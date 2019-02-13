import logging

import nltk
import progressbar
import regex

from .. import open_for_reading, extract_text_from_pdf


class StringToken(object):
	def __init__(self, original, gold=None, kbest=[]):
		self.original = original
		self.bin = dict()
		self.log = logging.getLogger(f'{__name__}.StringToken')
		# Newline characters are kept to recreate the text later,
		# but are replaced by labeled strings for writing to csv.
		if self.original == '\n':
			self.gold = '_NEWLINE_N_',
			self._kbest = [
				('_NEWLINE_N_', 1.0),
				('_NEWLINE_N_', 0.0)
			]
		elif self.original == '\r':
			self.gold = '_NEWLINE_R_',
			self._kbest = [
				('_NEWLINE_R_', 1.0),
				('_NEWLINE_R_', 0.0)
			]
		elif self.is_punctuation():
			#self.log.debug(f'{self}: is_punctuation')
			self.gold = self.original
			self._kbest = []
		else:
			self.gold = gold
			self._kbest = kbest
	
	def __str__(self):
		return f'<{self.__class__.__name__} {self.original}, {self.gold}, {self._kbest}, {self.bin}>'
	
	def __repr__(self):
		return self.__str__()
	
	def __eq__(self, other):
		if isinstance(other, self.__class__):
			return self.original.__eq__(other.original)
		elif isinstance(other, str):
			return self.original.__eq__(other)
		else:
			return False
	
	def __lt__(self, other):
		if isinstance(other, self.__class__):
			return self.original.__lt__(other.original)
		elif isinstance(other, str):
			return self.original.__lt__(other)
		else:
			return False
	
	def __hash__(self):
		return self.original.__hash__()
	
	def update(self, other=None, kbest=None, d=None, k=4):
		if other:
			if not self.original: self.original = other.original
			if not self.gold: self.gold = other.gold
			self._kbest = other._kbest
		elif kbest:
			self._kbest = kbest
		elif d:
			#self.log.debug(f'{self} -- {d}')
			kbest = []
			for n in range(1, k+1):
				candidate = d[f'{n}-best']
				probability = d[f'{n}-best prob.']
				if probability == '': # not sure why this sometimes happens...
					probability = 0.0
				kbest.append((candidate, float(probability)))
			self.__init__(
				d['Original'],
				d.get('Gold', None),
				kbest
			)
			#self.log.debug(self)
	
	def from_dict(d, k=4):
		t = StringToken('')
		t.update(d=d, k=k)
		return t
	
	def as_dict(self):
		output = {
			'Gold': self.gold or '',
			'Original': self.original,
		}
		for k, (candidate, probability) in enumerate(self._kbest, 1):
			output[f'{k}-best'] = candidate
			output[f'{k}-best prob.'] = probability
		if len(self.bin) > 0:
			output['bin'] = self.bin.get('number', -1)
			output['heuristic'] = self.bin.get('heuristic', None)
			output['decision'] = self.bin.get('decision', None)
			output['selection'] = self.bin.get('selection', None)
			
		return output
	
	def kbest(self, k=0):
		if k > 0:
			if k <= len(self._kbest):
				return self._kbest[k-1]
			else:
				return ('n/a', 0.0)
		elif self._kbest and len(self._kbest) > 0:
			return enumerate(self._kbest, 1)
		else:
			o = self.original
			return enumerate([(o, 1.0), (o, 0.0), (o, 0.0), (o, 0.0)], 1)
	
	punctuationRE = regex.compile(r'^\p{punct}+|``$')
	
	def is_punctuation(self):
		return StringToken.punctuationRE.match(self.original)
	
	def is_numeric(self):
		return self.original.isnumeric()


def tokenize_string(data, language='English', objectify=True):
	words = nltk.tokenize.word_tokenize(data, language)
	
	if not objectify:
		return words

	return [StringToken(w) for w in words]


def tokenize_file(filename, header=0, language='English', objectify=True):
	with open_for_reading(filename) as f:
		data = str.join('\n', [l for l in f.readlines()][header:])
	
	return tokenize_string(data, language, objectify=objectify)


class StringTokenizer(object):
	def __init__(self, dictionary, hmm, language, wordAlignments=None, previousTokens=None):
		self.log = logging.getLogger(f'{__name__}.StringTokenizer')
		self.dictionary = dictionary
		self.hmm = hmm
		self.language = language
		self.wordAlignments = wordAlignments
		self.previousTokens = previousTokens or dict()
		self.tokens = []

	def tokenize(self, file, nheaderlines=0, k=4, force=False):
		tokens = tokenize_file(file, nheaderlines, self.language)
		self.log.debug(f'Found {len(tokens)} tokens, first 10: {tokens[:10]}')
	
		self.log.info(f'Generating {k}-best suggestions for each token')
		for i, token in enumerate(progressbar.progressbar(tokens)):
			if token in self.previousTokens:
				token.update(other=self.previousTokens[token])
			else:
				token.update(kbest=self.hmm.kbest_for_word(token.original, k, self.dictionary))
			if not token.gold and token.original in self.wordAlignments:
				wa = self.wordAlignments.get(token.original, dict())
				closest = sorted(wa.items(), key=lambda x: x[0], reverse=True)
				#self.log.debug(f'{i} {token.original} {closest}')
				token.gold = closest[0][1]
			self.previousTokens[token.original] = token
			#self.log.debug(token.as_dict())

		return tokens

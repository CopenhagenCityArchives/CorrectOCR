import abc
import json
import logging
from typing import Dict, List, Tuple

import nltk
import progressbar
import regex
from PIL import Image
from lxml import html

from .. import punctuationRE


def tokenize_str(data: str, language='English') -> List[str]:
	return nltk.tokenize.word_tokenize(data, language)


##########################################################################################


class Token(abc.ABC):
	subclasses = dict()

	@staticmethod
	def register(cls):
		Token.subclasses[cls.__name__] = cls

	@property
	@abc.abstractmethod
	def original(self):
		pass

	@property
	@abc.abstractmethod
	def token_info(self):
		pass

	@property
	def k(self):
		return len(self._kbest)

	def __init__(self, gold: str = None, kbest: List[Tuple[str, float]] = None):
		self.bin = dict()
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
			#self.__class__.log.debug(f'{self}: is_punctuation')
			self.gold = self.original
			self._kbest = []
		else:
			self.gold = gold
			self._kbest = kbest
		if not self._kbest:
			self._kbest = []

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
			return NotImplemented

	def __lt__(self, other):
		if isinstance(other, self.__class__):
			return self.original.__lt__(other.original)
		elif isinstance(other, str):
			return self.original.__lt__(other)
		else:
			return NotImplemented

	def __hash__(self):
		return self.original.__hash__()

	punctuationRE = regex.compile(r'^\p{punct}+|``$')

	def is_punctuation(self):
		return Token.punctuationRE.match(self.original)

	def is_numeric(self):
		return self.original.isnumeric()

	def kbest(self, k=0):
		if k > 0:
			if k <= len(self._kbest):
				return self._kbest[k-1]
			else:
				return 'n/a', 0.0
		elif self._kbest and len(self._kbest) > 0:
			return enumerate(self._kbest, 1)
		else:
			o = self.original
			return enumerate([(o, 1.0), (o, 0.0)], 1)

	def as_dict(self):
		output = {
			'Gold': self.gold or '',
			'Original': self.original,
		}
		for k, (candidate, probability) in enumerate(self._kbest, 1):
			output[f'{k}-best'] = candidate
			output[f'{k}-best prob.'] = probability
		if len(self.bin) > 0:
			output['Bin'] = self.bin.get('number', -1)
			output['Heuristic'] = self.bin.get('heuristic', None)
			output['Decision'] = self.bin.get('decision', None)
			output['Selection'] = self.bin.get('selection', None)
		output['Token type'] = self.__class__.__name__
		output['Token info'] = json.dumps(self.token_info)

		return output

	@classmethod
	def from_dict(cls, d: dict) -> 'Token':
		classname = d['Token type']
		#Token.subclasses[classname].log.debug(f'{d}')
		t = Token.subclasses[classname](json.loads(d['Token info']))
		t.update(d=d)
		return t

	def update(self, other: 'Token' = None, kbest: List[Tuple[str, float]] = None, d: dict = None):
		if other:
			#self.__class__.log.debug(f'{self} -- {other}')
			if not self.gold: self.gold = other.gold
			self._kbest = other._kbest
		elif kbest:
			#self.__class__.log.debug(f'{self} -- {kbest}')
			self._kbest = kbest
		elif d:
			#self.__class__.log.debug(f'{self} -- {d}')
			kbest = []
			k = 1
			while f'{k}-best' in d:
				candidate = d[f'{k}-best']
				probability = d[f'{k}-best prob.']
				if probability == '': # not sure why this sometimes happens...
					probability = 0.0
				kbest.append((candidate, float(probability)))
				k += 1
			self.gold = d.get('Gold', None)
			self._kbest = kbest
			#self.__class__.log.debug(self)


##########################################################################################


class Tokenizer(abc.ABC):
	log = logging.getLogger(f'{__name__}.Tokenizer')
	subclasses = dict()

	@staticmethod
	def register(cls, extensions):
		for ext in extensions:
			Tokenizer.subclasses[ext] = cls

	@staticmethod
	def for_extension(ext):
		Tokenizer.log.debug(f'subclasses: {Tokenizer.subclasses}')
		return Tokenizer.subclasses[ext]

	def __init__(self, dictionary, hmm, language, k=4, wordAlignments=None, previousTokens: Dict[str, Token] = None):
		self.dictionary = dictionary
		self.hmm = hmm
		self.language = language
		self.k = k
		self.wordAlignments = wordAlignments
		self.previousTokens = previousTokens or dict()
		self.tokens = []

	@abc.abstractmethod
	def tokenize(self, file, force):
		pass

	@staticmethod
	@abc.abstractmethod
	def apply(original, tokens: List[Token], corrected):
		pass

	def generate_kbest(self, tokens: List[Token]) -> List[Token]:
		if len(tokens) == 0:
			Tokenizer.log.error(f'No tokens were supplied?!')
			raise SystemExit(-1)

		Tokenizer.log.info(f'Generating {self.k}-best suggestions for each token')
		for i, token in enumerate(progressbar.progressbar(tokens)):
			original = punctuationRE.sub('', token.original)
			if original in self.previousTokens:
				token.update(other=self.previousTokens[original])
			else:
				token.update(kbest=self.hmm.kbest_for_word(original, self.k))
			if not token.gold and original in self.wordAlignments:
				wa = self.wordAlignments.get(original, dict())
				closest = sorted(wa.items(), key=lambda x: x[0], reverse=True)
				#Tokenizer.log.debug(f'{i} {token.original} {closest}')
				token.gold = closest[0][1]
			self.previousTokens[original] = token
			#Tokenizer.log.debug(token.as_dict())

		Tokenizer.log.debug(f'Generated for {len(tokens)} tokens, first 10: {tokens[:10]}')
		return tokens


##########################################################################################


class TokenSegment(object):
	log = logging.getLogger(f'{__name__}.TokenSegment')

	def __init__(self, fileid: str, page: int, column: int, rect: Tuple[int, int, int, int], image: Image, hocr: html.Element, tokens: List[Token]):
		self.fileid = fileid
		self.page = page
		self.column = column
		self.rect = rect
		self.image = image
		self.hocr = hocr
		self.tokens = tokens


##########################################################################################


def dehyphenate_tokens(tokens: List[Token]) -> List[Token]:
	log = logging.getLogger(f'{__name__}.dehyphenate_tokens')
	r = regex.compile(r'\p{Dash}$') # ends in char from 'Dash' category of Unicode

	dehyphenated = []
	tokens = iter(tokens)
	for token in tokens:
		if r.search(token.original):
			newtoken = DehyphenationToken(token, next(tokens))
			log.debug(f'Dehyphenated: {newtoken}')
			dehyphenated.append(newtoken)
		else:
			dehyphenated.append(token)

	return dehyphenated


class DehyphenationToken(Token):
	def __init__(self, first: Token, second: Token):
		self.first = first
		self.second = second
		super().__init__()

	@property
	def original(self):
		return f'{self.first.original[:-1]}{self.second.original}'

	@property
	def token_info(self):
		return {'first': self.first, 'second': self.second}

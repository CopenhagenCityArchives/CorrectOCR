import abc
from typing import List, Tuple

import nltk
import regex

def tokenize_str(data: str, language='English') -> List[str]:
	return nltk.tokenize.word_tokenize(data, language)


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
		output['Token info'] = self.token_info

		return output

	@classmethod
	def from_dict(cls, d: dict) -> 'Token':
		classname = d['Token type']
		t = Token.subclasses[classname](d['Token info'] or d['Original'])
		t.update(d=d)
		return t

	def update(self, other: 'Token' = None, kbest: List[Tuple[str, float]] = None, d: dict = None):
		if other:
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


class Tokenizer(abc.ABC):
	@abc.abstractmethod
	def tokenize(self, file, force):
		pass

import abc
import collections
import json
import logging
import string
from pathlib import Path
from typing import Any, DefaultDict, List, NamedTuple, Tuple

import nltk
import regex
from lxml import html


from ..heuristics import Bin


def tokenize_str(data: str, language='English') -> List[str]:
	return nltk.tokenize.word_tokenize(data, language)


##########################################################################################


class KBestItem(NamedTuple):
	candidate: str = ''
	probability: float = 0.0

	def __repr__(self) -> str:
		return f'<KBestItem {self.candidate}, {self.probability:.2e}>'


##########################################################################################


class Token(abc.ABC):
	subclasses = dict()

	@staticmethod
	def register(cls):
		Token.subclasses[cls.__name__] = cls
		return cls

	punct_RE = regex.compile(r'^(\p{punct}*)(.*?)(\p{punct}*)$')

	@property
	@abc.abstractmethod
	def token_info(self):
		pass

	@property
	def original(self):
		return f'{self._punct_prefix}{self.lookup}{self._punct_suffix}'

	@property
	def gold(self):
		return f'{self._punct_prefix}{self._gold}{self._punct_suffix}' if self._gold is not None else None

	@gold.setter
	def gold(self, gold):
		self._gold = gold
		if self._gold:
			self._gold = self._gold.lstrip(string.punctuation).rstrip(string.punctuation)

	@property
	def k(self):
		return len(self.kbest)

	def __init__(self, original: str):
		m = Token.punct_RE.search(original)
		(self._punct_prefix, self.lookup, self._punct_suffix) = m.groups('')
		self.gold = None
		self.bin: Bin = None
		self.kbest: DefaultDict[int, KBestItem] = collections.defaultdict(KBestItem)
		
		if self.is_punctuation():
			#self.__class__.log.debug(f'{self}: is_punctuation')
			self._gold = self.lookup

	def __str__(self):
		return f'<{self.__class__.__name__} "{self.original}" "{self.gold}" {self.kbest} {self.bin}>'

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

	punctuationRE = regex.compile(r'^\p{punct}+$')

	def is_punctuation(self):
		#self.__class__.log.debug(f'{self}')
		return Token.punctuationRE.match(self.original)

	def is_numeric(self):
		return self.original.isnumeric()

	@property
	def __dict__(self):
		output = {
			'Gold': self.gold or '',
			'Original': self.original,
		}
		for k, item in self.kbest.items():
			output[f'{k}-best'] = item.candidate
			output[f'{k}-best prob.'] = item.probability
		if self.bin:
			output['Bin'] = self.bin.number or -1
			output['Heuristic'] = self.bin.heuristic
			output['Decision'] = self.bin.decision
			output['Selection'] = self.bin.selection
		output['Token type'] = self.__class__.__name__
		output['Token info'] = json.dumps(self.token_info)

		return output

	@classmethod
	def from_dict(cls, d: dict) -> 'Token':
		classname = d['Token type']
		#Token.subclasses[classname].log.debug(f'from_dict: {d}')
		t = Token.subclasses[classname](json.loads(d['Token info']))
		t.gold = d.get('Gold', None)
		kbest = collections.defaultdict(lambda: KBestItem(''))
		k = 1
		while f'{k}-best' in d:
			candidate = d[f'{k}-best']
			if candidate == '':
				break
			probability = d[f'{k}-best prob.']
			kbest[k] = KBestItem(candidate, float(probability))
			k += 1
		t.kbest = kbest
		if 'Bin' in d:
			from ..heuristics import Heuristics
			t.bin = Heuristics.bins[int(d['Bin'])].copy()
			t.bin.heuristic = d['Heuristic']
			t.bin.decision = d['Decision']
			t.bin.selection = d['Selection']
		#t.__class__.log.debug(t)
		return t

	@property
	def header(self) -> List[str]:
		header = ['Original']
		if self.gold:
			header = ['Gold'] + header
		for k in range(1, self.k+1):
			header += [f'{k}-best', f'{k}-best prob.']
		if self.bin:
			header += ['Bin', 'Heuristic', 'Decision', 'Selection']
		return header + ['Token type', 'Token info']


##########################################################################################


class Tokenizer(abc.ABC):
	log = logging.getLogger(f'{__name__}.Tokenizer')
	subclasses = dict()

	@staticmethod
	def register(extensions):
		def wrapper(cls):
			for ext in extensions:
				Tokenizer.subclasses[ext] = cls
			return cls
		return wrapper

	@staticmethod
	def for_extension(ext):
		Tokenizer.log.debug(f'subclasses: {Tokenizer.subclasses}')
		return Tokenizer.subclasses[ext]

	def __init__(self, language):
		self.language = language
		self.tokens = []

	@abc.abstractmethod
	def tokenize(self, file, force):
		pass

	@staticmethod
	@abc.abstractmethod
	def apply(original, tokens: List[Token], corrected):
		pass


##########################################################################################


class TokenSegment(NamedTuple):
	fileid: str
	page: int
	column: int
	rect: Tuple[float, float, float, float]
	image: Any # PIL.Image doesnt work...?
	hocr: html.Element
	tokens: List[Token]


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
		super().__init__(self.original)

	@property
	def original(self):
		return f'{self.first.original[:-1]}{self.second.original}'

	@property
	def token_info(self):
		return {'first': self.first, 'second': self.second}

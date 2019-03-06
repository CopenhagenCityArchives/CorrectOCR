import abc
import collections
import json
import logging
from typing import Dict, List, DefaultDict, Tuple, NamedTuple

import nltk
import progressbar
import regex
from PIL import Image
from lxml import html


def tokenize_str(data: str, language='English') -> List[str]:
	return nltk.tokenize.word_tokenize(data, language)


##########################################################################################


class KBestItem(NamedTuple):
	candidate: str
	probability: float = 0.0

	def __repr__(self) -> str:
		return f'<KBestItem {self.candidate}, {self.probability:.2e}>'


##########################################################################################


class Token(abc.ABC):
	subclasses = dict()

	@staticmethod
	def register(cls):
		Token.subclasses[cls.__name__] = cls

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

	@property
	def k(self):
		return len(self.kbest)

	def __init__(self, original: str):
		m = Token.punct_RE.search(original)
		(self._punct_prefix, self.lookup, self._punct_suffix) = m.groups('')
		self.gold = None
		self.bin = dict()
		self.kbest: DefaultDict[int, KBestItem] = collections.defaultdict(lambda: KBestItem(''))
		
		if self.is_punctuation():
			#self.__class__.log.debug(f'{self}: is_punctuation')
			self._gold = self.lookup

	def __str__(self):
		return f'<{self.__class__.__name__} {self.original}, {self.gold}, {self.kbest}, {self.bin}>'

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

	@property
	def __dict__(self):
		output = {
			'Gold': self.gold or '',
			'Original': self.original,
		}
		for k, item in self.kbest.items():
			output[f'{k}-best'] = item.candidate
			output[f'{k}-best prob.'] = item.probability
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
		t.gold = d.get('Gold', None)
		kbest = collections.defaultdict(lambda: KBestItem(''))
		k = 1
		while f'{k}-best' in d:
			candidate = d[f'{k}-best']
			probability = d[f'{k}-best prob.']
			kbest[k] = KBestItem(candidate, float(probability))
			k += 1
		t.kbest = kbest
		#t.__class__.log.debug(t)
		return t


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
			if token.lookup in self.previousTokens:
				token.kbest = self.previousTokens[token.lookup].kbest
			else:
				token.kbest = self.hmm.kbest_for_word(token.lookup, self.k)
			if not token.gold and token.lookup in self.wordAlignments:
				wa = self.wordAlignments.get(token.lookup, dict())
				closest = sorted(wa.items(), key=lambda x: x[0], reverse=True)
				#Tokenizer.log.debug(f'{i} {token.token.lookup} {closest}')
				token.gold = closest[0][1]
			self.previousTokens[token.lookup] = token
			#Tokenizer.log.debug(vars(token))

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
		super().__init__(self.original)

	@property
	def original(self):
		return f'{self.first.original[:-1]}{self.second.original}'

	@property
	def token_info(self):
		return {'first': self.first, 'second': self.second}

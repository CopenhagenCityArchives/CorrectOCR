from __future__ import annotations

import abc
import collections
import json
import logging
import string
from pathlib import Path
from typing import Any, DefaultDict, List, NamedTuple, Optional

import nltk
import regex

from .list import TokenList
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
	"""
	Abstract base class. Tokens handle single words. ...
	"""
	_subclasses = dict()

	@staticmethod
	def register(cls):
		"""
		Decorator which registers a :class:`Token` subclass with the base class.

		:param cls: Token subclass
		"""
		Token._subclasses[cls.__name__] = cls
		return cls

	_punctuation_splitter = regex.compile(r'^(\p{punct}*)(.*?)(\p{punct}*)$')

	def __init__(self, original: str, docid: str, index: int):
		"""
		:param original: Original spelling of the token.
		:param docid: The doc with which the Token is associated.
		"""
		m = Token._punctuation_splitter.search(original)
		(self._punct_prefix, self.normalized, self._punct_suffix) = m.groups('')
		self.docid = docid  #: The doc with which the Token is associated.
		self.index = index #: The placement of the Token in the doc.
		self.gold = None
		self.bin: Optional[Bin] = None  #: Heuristics bin.
		self.kbest: DefaultDict[int, KBestItem] = collections.defaultdict(KBestItem)
		"""
		Dictionary of *k*-best suggestions for the Token. They are keyed
		with a numerical index starting at 1, and the values are instances
		of :class:`KBestItem`.
		"""
		self.decision: Optional[str] = None #: The decision that was made when :attr:`gold` was set automatically.
		self.selection: Any = None #: The selected automatic correction for the :attr:`decision`.
		self.is_hyphenated = False #: Whether the token is hyphenated to the following token.

		if self.is_punctuation():
			#self.__class__.log.debug(f'{self}: is_punctuation')
			self._gold = self.normalized

	@property
	@abc.abstractmethod
	def token_info(self) -> Any:
		"""

		:return:
		"""
		pass

	@property
	def original(self) -> str:
		"""
		The original spelling of the Token.
		"""
		return f'{self._punct_prefix}{self.normalized}{self._punct_suffix}'

	@property
	def gold(self) -> str:
		"""
		The corrected spelling of the Token.
		"""
		return f'{self._punct_prefix}{self._gold}{self._punct_suffix}' if self._gold is not None else None

	@gold.setter
	def gold(self, gold):
		self._gold = gold
		if self._gold:
			self._gold = self._gold.lstrip(string.punctuation).rstrip(string.punctuation)

	@property
	def k(self) -> int:
		"""
		The number of *k*-best suggestions for the Token.
		"""
		return len(self.kbest)

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

	_is_punctuationRE = regex.compile(r'^\p{punct}+$')

	def is_punctuation(self) -> bool:
		"""
		Is the Token purely punctuation?
		"""
		#self.__class__.log.debug(f'{self}')
		return Token._is_punctuationRE.match(self.original)

	def is_numeric(self) -> bool:
		"""
		Is the Token purely numeric?
		"""
		return self.original.isnumeric()

	@property
	def __dict__(self):
		output = {
			'Gold': self.gold or '',
			'Original': self.original,
			'Doc ID': self.docid,
			'Index': self.index,
			'Hyphenated': self.is_hyphenated,
		}
		for k, item in self.kbest.items():
			output[f'{k}-best'] = item.candidate
			output[f'{k}-best prob.'] = item.probability
		if self.bin:
			output['Bin'] = self.bin.number or -1
			output['Heuristic'] = self.bin.heuristic
			output['Decision'] = self.decision
			output['Selection'] = self.selection
		output['Token type'] = self.__class__.__name__
		output['Token info'] = json.dumps(self.token_info)

		return output

	@classmethod
	def from_dict(cls, d: dict) -> Token:
		"""
		Initialize and return a new Token with values from a dictionary.

		:param d: A dictionary of properties for the Token
		"""
		classname = d['Token type']
		#Token._subclasses[classname].log.debug(f'from_dict: {d}')
		t = Token._subclasses[classname](
			json.loads(d['Token info']),
			d.get('Doc ID', None),
			d.get('Index', -1)
		)
		t.gold = d.get('Gold', None)
		t.hyphenated = d.get('Hyphenated', False)
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
		if 'Bin' in d and d['Bin'] != '':
			from ..heuristics import Heuristics
			t.bin = Heuristics.bin(int(d['Bin']))
			t.bin.heuristic = d['Heuristic']
			t.decision = d['Decision']
			t.selection = d['Selection']
		#t.__class__.log.debug(t)
		return t


##########################################################################################


class Tokenizer(abc.ABC):
	"""
	Abstract base class. The `Tokenizer` subclasses handle extracting :class:`Token` instances from a document.
	"""
	log = logging.getLogger(f'{__name__}.Tokenizer')
	_subclasses = dict()

	@staticmethod
	def register(extensions: List[str]):
		"""
		Decorator which registers a :class:`Tokenizer` subclass with the base class.

		:param extensions: List of extensions that the subclass will handle
		"""
		def wrapper(cls):
			for ext in extensions:
				Tokenizer._subclasses[ext] = cls
			return cls
		return wrapper

	@staticmethod
	def for_extension(ext: str) -> TokenList.__class__:
		"""
		Obtain the suitable subclass for the given extension. Currently, Tokenizers are
		provided for the following extensions:

		-  ``.txt`` -- plain old text.
		-  ``.pdf`` -- assumes the PDF contains images and OCRed text.
		-  ``.tiff`` -- will run OCR on the image and generate a PDF.
		-  ``.png`` -- will run OCR on the image and generate a PDF.

		:param ext: Filename extension (including leading period).
		:return: A Tokenizer subclass.
		"""
		Tokenizer.log.debug(f'_subclasses: {Tokenizer._subclasses}')
		return Tokenizer._subclasses[ext]

	def __init__(self, language, dehyphenate):
		"""

		:type language: :class:`pycountry.Language`
		:param language: The language to use for tokenization (for example, the `.txt` tokenizer internally uses nltk whose tokenizers function best with a language parameter).
		"""
		self.language = language
		self.dehyphenate = dehyphenate
		self.tokens = []

	@abc.abstractmethod
	def tokenize(self, file: Path, storageconfig) -> TokenList:
		"""
		Generate tokens for the given document.

		:param storageconfig: Storage configuration (database, filesystem) for resulting Tokens
		:param file: A given document.
		:return:
		"""
		pass

	@staticmethod
	@abc.abstractmethod
	def apply(original: Path, tokens: TokenList, corrected: Path):
		pass

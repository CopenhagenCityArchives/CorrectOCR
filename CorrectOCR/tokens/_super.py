from __future__ import annotations

import abc
import collections
import datetime
import json
import logging
import string
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, DefaultDict, List, NamedTuple, Optional, Tuple

import nltk
from dataclasses_json import DataClassJsonMixin

from .list import TokenList
from .._util import punctuationRE
from ..fileio import FileIO
from ..heuristics import Bin
from ..model.kbest import KBestItem


def tokenize_str(data: str, language='english') -> List[str]:
	return nltk.tokenize.word_tokenize(data, language.lower())


##########################################################################################


class CorrectOCRDictMixin(DataClassJsonMixin):
	def to_dict(self) -> Dictionary:
		d = super(DataClassJsonMixin, self).to_dict()
		d['token_info'] = self.__class__.__name__
		return d

	@classmethod
	def from_dict(cls, d: dict) -> Token:
		"""
		Initialize and return a new Token with values from a dictionary.

		:param d: A dictionary of properties for the Token
		"""
		print(('from_dict: ', cls, type(cls), Token.__class__))
		if cls == Token:
			sc = Token._subclasses[d['token_type']]
			print(('sublass: ', sc))
			return sc.from_dict(d)
		else:
			return cls.from_dict(d)


@dataclass
class Token(CorrectOCRDictMixin, abc.ABC):
	"""
	Abstract base class. Tokens handle single words. ...
	"""
	_subclasses = dict()
	original: str #: Original spelling of the token.
	docid: str #: The document with which the Token is associated.
	index: int #: The token's index in the document.
	gold: str = None #: The corrected spelling of the token.
	is_hyphenated: bool = False #: Whether the token is hyphenated to the following token.
	is_discarded: bool = False #: Whether the token has been discarded.
	has_error:bool = False #: Whether the token currently has an unhandled error.

	token_info: Any = None #: An opaque bit of data that the various token types may use internally.

	"""
	Dictionary of *k*-best suggestions for the Token. They are keyed
	with a numerical index starting at 1, and the values are instances
	of :class:`KBestItem`.
	"""
	kbest: DefaultDict[int, KBestItem] = field(default_factory=lambda: collections.defaultdict(KBestItem))
	
	#heuristics:
	bin: Bin = None  #: Heuristics bin.
	heuristic: str = None #: The heuristic that was was determined by the bin.
	selection: Any = None #: The selected automatic correction for the :attr:`heuristic`.

	annotations: List[Any] = field(default_factory=list) #: A list of arbitrary key/value info about the annotations
	last_modified: datetime.datetime = None #: When one of the ``gold``, ``ìs_hyphenated``, ``is_discarded``, or ``has_error`` properties was last updated.


	def __post_init__(self):
		#print(self.__class__)
		#print(self.__class__.__bases__)
		#print(sorted(self.__dir__()))
		#print(sorted(super().__dir__()))
		#print(vars(self))
		self.cached_image_path = FileIO.imageCache(self.docid).joinpath(
			f'{self.index}.png'
		) #: Where the image file should be cached. Is not guaranteed to exist, but can be generated via extract_image()

		if self.is_punctuation():
			#self.__class__.log.debug(f'{self}: is_punctuation')
			self._gold = self.original

	def __setattr__(self, attr, value):
		super().__setattr__(attr, value)
		if attr in ('gold', 'is_hyphenated', 'is_discarded', 'has_error'):
			self.last_modified = datetime.datetime.now()
		if attr == 'is_discarded' and value is True:
			self.gold = ''

	def __repr__(self):
		return f'{self.__class__.__name__}({vars(self)})'

	@staticmethod
	def register(cls):
		"""
		Decorator which registers a :class:`Token` subclass with the base class.

		:param cls: Token subclass
		"""
		Token._subclasses[cls.__name__] = cls
		return cls

	@property
	@abc.abstractmethod
	def page(self) -> int:
		"""
		The page of the document on which the token is located.
		
		May not be applicable for all token types.
		
		:return: The page number.
		"""
		return None

	@property
	@abc.abstractmethod
	def frame(self) -> (int, int, int, int):
		"""
		The coordinates of the token's location on the page.
		
		Takes the form [x0, y0, x1, y1] where (x0, y0) is the top-left corner, and
		(x1, y1) is the bottom-right corner.
		
		May not be applicable for all token types.
		
		:return: The frame coordinates.
		"""
		return None

	@property
	def k(self) -> int:
		"""
		The number of *k*-best suggestions for the Token.
		"""
		return len(self.kbest)

	def __hash__(self):
		return self.original.__hash__()

	def is_punctuation(self) -> bool:
		"""
		Is the Token purely punctuation?
		"""
		#self.__class__.log.debug(f'{self}')
		return punctuationRE.fullmatch(self.original)

	def is_numeric(self) -> bool:
		"""
		Is the Token purely numeric?
		"""
		return self.original.isnumeric()

	def drop_cached_image(self):
		if self.cached_image_path.is_file():
			try:
				self.cached_image_path.unlink()
			except:
				self.__class__.log.error(f'Could not delete image:\n{traceback.format_exc()}')

	def extract_image(self, workspace, highlight_word=True, left=300, right=300, top=15, bottom=15, force=False) -> Tuple[Path, Any]:
		pass


##########################################################################################


class Tokenizer(abc.ABC):
	"""
	Abstract base class. The `Tokenizer` subclasses handle extracting :class:`Token` instances from a document.
	"""
	log = logging.getLogger(f'{__name__}.Tokenizer')
	_subclasses = dict()

	@staticmethod
	def register(filetypes: List[str]):
		"""
		Decorator which registers a :class:`Tokenizer` subclass with the base class.

		:param filetypes: List of extensions or mimetypes that the subclass will handle
		"""
		def wrapper(cls):
			for filetype in filetypes:
				Tokenizer._subclasses[filetype] = cls
			return cls
		return wrapper

	@staticmethod
	def for_type(filetype: str) -> TokenList.__class__:
		"""
		Obtain the suitable subclass for the given extension. Currently, Tokenizers are
		provided for the following extensions:

		-  ``.txt`` / ``text/plain`` -- plain old text.
		-  ``.pdf`` / ``application/pdf`` -- assumes the PDF contains images and OCRed text.
		-  ``.tiff`` / ``image/tiff`` -- will run OCR on the image and generate a PDF.
		-  ``.png`` / ``image/png`` -- will run OCR on the image and generate a PDF.

		:param filetype: Filename extension (including leading period) or mimetype.
		:return: A Tokenizer subclass.
		"""
		Tokenizer.log.debug(f'_subclasses: {Tokenizer._subclasses}')
		return Tokenizer._subclasses[filetype]

	def __init__(self, language):
		"""

		:type language: :class:`pycountry.Language`
		:param language: The language to use for tokenization (for example, the `.txt` tokenizer internally uses nltk whose tokenizers function best with a language parameter).
		"""
		self.language = language
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
	def apply(original: Path, tokens: TokenList, outfile: Path, highlight=False):
		pass

	@staticmethod
	@abc.abstractmethod
	def crop_tokens(original, config, tokens, edge_left = None, edge_right = None):
		pass

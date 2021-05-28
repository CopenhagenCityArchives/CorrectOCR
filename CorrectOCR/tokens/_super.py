from __future__ import annotations

import abc
import collections
import datetime
import json
import logging
import string
import traceback
from pathlib import Path
from typing import Any, DefaultDict, List, NamedTuple, Optional, Tuple

import nltk

from .list import TokenList
from .._util import punctuation_splitter, punctuationRE
from ..fileio import FileIO
from ..heuristics import Bin
from ..model.kbest import KBestItem


def tokenize_str(data: str, language='english') -> List[str]:
	return nltk.tokenize.word_tokenize(data, language.lower())


##########################################################################################


class UpdateModifiedAccess:
	def __set_name__(self, owner, name):
		self.public_name = name
		self.private_name = '_' + name
		self.post_effect_name = '_post_' + name

	def __get__(self, obj, objtype=None):
		return getattr(obj, self.private_name)

	def __set__(self, obj, value):
		obj.last_modified = datetime.datetime.now()
		setattr(obj, self.private_name, value)
		if hasattr(obj, self.post_effect_name):
			getattr(obj, self.post_effect_name)(value)


##########################################################################################


class Token(abc.ABC):
	"""
	Abstract base class. Tokens handle single words. ...
	"""
	_subclasses = dict()
	gold = UpdateModifiedAccess()
	is_hyphenated = UpdateModifiedAccess()
	is_discarded = UpdateModifiedAccess()

	def _post_is_discarded(self, value):
		if value is True:
			self.gold = ''

	@staticmethod
	def register(cls):
		"""
		Decorator which registers a :class:`Token` subclass with the base class.

		:param cls: Token subclass
		"""
		Token._subclasses[cls.__name__] = cls
		return cls

	def __init__(self, original: str, docid: str, index: int):
		"""
		:param original: Original spelling of the token.
		:param docid: The doc with which the Token is associated.
		"""
		if type(self) is Token:
			raise TypeError("Token base class cannot not be directly instantiated")
		if docid is None:
			raise ValueError('Tokens must have a docid!')
		if index is None:
			raise ValueError('Tokens must have an index!')
		self.original = original
		_, self.normalized, _ = punctuation_splitter(self.original)
		self.docid = docid  #: The doc with which the Token is associated.
		self.index = index #: The placement of the Token in the doc.
		self.gold = None # (documented in @property methods below)
		self.bin: Optional[Bin] = None  #: Heuristics bin.
		self.kbest: DefaultDict[int, KBestItem] = collections.defaultdict(KBestItem)
		"""
		Dictionary of *k*-best suggestions for the Token. They are keyed
		with a numerical index starting at 1, and the values are instances
		of :class:`KBestItem`.
		"""
		self.decision: Optional[str] = None #: The decision that was made when :attr:`gold` was set automatically.
		self.selection: Any = None #: The selected automatic correction for the :attr:`decision`.
		self.is_hyphenated = False # (documented in @property methods below)
		self.is_discarded = False #: (documented in @property methods below)

		self.annotation_info = {} #: An arbitrary key/value store of information about the annotations
		self.last_modified = None #: When one of the ``gold``, ``ìs_hyphenated``, or ``is_discarded`` properties were last updated.

		self.cached_image_path = FileIO.cachePath(f'images/{self.docid}').joinpath(
			f'{self.index}.png'
		) #: Where the image file should be cached. Is not guaranteed to exist, but can be generated via extract_image()

		if self.is_punctuation():
			#self.__class__.log.debug(f'{self}: is_punctuation')
			self._gold = self.normalized

	@property
	@abc.abstractmethod
	def token_info(self) -> Any:
		"""

		:return:
		"""
		return None

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

	def __str__(self):
		return f'<{self.__class__.__name__} {vars(self)}>'

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

	@property
	def __dict__(self):
		output = {
			'Gold': self.gold,
			'Original': self.original,
			'Doc ID': self.docid,
			'Index': self.index,
			'Hyphenated': self.is_hyphenated,
			'Discarded': self.is_discarded,
			'Page': self.page,
			'Frame': self.frame,
		}
		output['k-best'] = dict()
		for k, item in self.kbest.items():
			output['k-best'][k] = vars(item)
		if self.bin:
			output['Bin'] = self.bin.number
			output['Heuristic'] = self.bin.heuristic
		#else:
		#	raise ValueError(f'Bin missing in __dict__(): {t}')
		output['Decision'] = self.decision
		output['Selection'] = self.selection
		output['Token type'] = self.__class__.__name__
		output['Token info'] = json.dumps(self.token_info)
		output['Annotation info'] = json.dumps(self.annotation_info)
		output['Last Modified'] = self.last_modified.timestamp() if self.last_modified else None

		return output

	@classmethod
	def from_dict(cls, d: dict) -> Token:
		"""
		Initialize and return a new Token with values from a dictionary.

		:param d: A dictionary of properties for the Token
		"""
		if not isinstance(d, collections.Mapping):
			raise ValueError(f'Object is not dict-like: {d}')
		classname = d['Token type']
		#self.__class__.log.debug(f'from_dict: {d}')
		t = Token._subclasses[classname](
			json.loads(d['Token info']),
			d['Doc ID'],
			d['Index']
		)
		t.gold = d.get('Gold', None)
		t.is_hyphenated = d.get('Hyphenated', False)
		t.is_discarded = d.get('Discarded', False)
		t.annotation_info = json.loads(d['Annotation info'])

		t.last_modified = d['Last Modified'] if 'Last Modified' in d else None
		if 'k-best' in d:
			kbest = collections.defaultdict(KBestItem)
			for k, b in d['k-best'].items():
				kbest[k] = KBestItem(b['candidate'], b['probability'])
			t.kbest = kbest
		if 'Bin' in d and d['Bin'] not in ('', '-1', -1):
			from ..heuristics import Heuristics
			t.bin = Heuristics.bin(int(d['Bin']))
			t.bin.heuristic = d['Heuristic']
		#else:
		#	raise ValueError(f'Bin: {d.get("Bin", None)} in from_dict(): {t}')
		t.decision = d.get('Decision', None)
		t.selection = d.get('Selection', None)
		#t.__class__.log.debug(t)
		return t

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
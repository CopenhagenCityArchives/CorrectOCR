from __future__ import annotations

import functools
import logging
import re
from pathlib import Path
from pprint import pformat
from typing import Dict, Iterator, Tuple, Union

from ._cache import LRUCache, cached
from .aligner import Aligner
from .dictionary import Dictionary
from .fileio import FileIO
from .heuristics import Heuristics
from .model import HMM
from .tokens import Token, Tokenizer, TokenList, tokenize_str


class Workspace(object):
	"""
	The Workspace holds references to :class:`Documents<CorrectOCR.workspace.Document>` and resources used by the various :mod:`commands<CorrectOCR.commands>`.

	:param workspaceconfig: An object with the following properties:

	   -  **nheaderlines** (:class:`int`): The number of header lines in corpus texts.
	   -  **language**: A language instance from `pycountry <https://pypi.org/project/pycountry/>`.
	   -  **originalPath** (:class:`Path<pathlib.Path>`): Directory containing the original docs.
	   -  **goldPath** (:class:`Path<pathlib.Path>`): Directory containing the gold (if any) docs.
	   -  **trainingPath** (:class:`Path<pathlib.Path>`): Directory for storing intermediate docs.
	   -  **correctedPath** (:class:`Path<pathlib.Path>`): Directory for saving corrected docs.

	:param resourceconfig: Passed directly to :class:`ResourceManager<CorrectOCR.workspace.ResourceManager>`, see this for further info.
	
	:param storageconfig: TODO
	"""
	log = logging.getLogger(f'{__name__}.Workspace')

	def __init__(self, workspaceconfig, resourceconfig, storageconfig):
		self.config = workspaceconfig
		self.storageconfig = storageconfig
		self.root = self.config.rootPath.resolve()
		Workspace.log.info(f'Workspace configuration:\n{pformat(vars(self.config))} at {self.root}')
		Workspace.log.info(f'Storage configuration:\n{pformat(vars(self.storageconfig))}')
		self.nheaderlines: int = self.config.nheaderlines
		self.resources = ResourceManager(self.root, resourceconfig)
		self.docs: Dict[str, Document] = dict()
		for file in self.config.originalPath.iterdir():
			if file.name in {'.DS_Store'}:
				continue
			self.add_docid(file.stem, file.suffix)
		Workspace.log.debug(f'docs: {self.docs}')
		self.cache = LRUCache(maxsize=1000)
		self.cachePath = FileIO.cachePath

	def add_docid(self, docid: str, ext: str, new_original: Path = None):
		"""
		Initializes a new :class:`Document<CorrectOCR.workspace.Document>` with a ``docid`` and adds it to the
		workspace.

		:param docid: The docid (filename without extension).
		:param ext: The extension, including leading period.
		:param new_original: Path to a new file that should be copied to the generated `originalPath`.
		"""
		if new_original:
			FileIO.copy(new_original, self._originalPath)
		self.docs[docid] = Document(
			self,
			docid,
			ext,
			self.root.joinpath(self.config.originalPath).resolve(),
			self.root.joinpath(self.config.goldPath).resolve(),
			self.root.joinpath(self.config.trainingPath).resolve(),
			self.root.joinpath(self.config.correctedPath).resolve(),
			self.nheaderlines,
		)
		Workspace.log.debug(f'Added {docid}')

	def docids_for_ext(self, ext: str) -> List[str]:
		"""
		Returns a list of IDs for documents with the given extension.
		"""
		return [docid for docid, doc in self.docs.items() if doc.ext == ext]

	def originalTokens(self) -> Iterator[Tuple[str, TokenList]]:
		"""
		Yields an iterator of (docid, list of tokens).
		"""
		for docid, doc in self.docs.items():
			if doc.originalTokenFile.is_file():
				Workspace.log.debug(f'Getting original tokens from {docid}')
				yield docid, [Token.from_dict(row) for row in FileIO.load(doc.originalTokenFile)]

	def goldTokens(self) -> Iterator[Tuple[str, TokenList]]:
		"""
		Yields an iterator of (docid, list of gold-aligned tokens).
		"""
		for docid, doc in self.docs.items():
			if doc.alignedTokenFile.is_file():
				Workspace.log.debug(f'Getting gold tokens from {docid}')
				yield docid, [Token.from_dict(row) for row in FileIO.load(doc.alignedTokenFile)]

	def cleanup(self, dryrun=True, full=False):
		"""
		Cleans out the backup files in the ``trainingPath``.

		:param dryrun: Just lists the files without actually deleting them
		:param full: Also deletes the current files (ie. those without .nnn. in their suffix).
		"""
		is_backup = re.compile(r'^\.\d\d\d$')

		for file in self._trainingPath.iterdir():
			if file.name[0] == '.':
				continue
			#self.log.debug(f'file: {file}')
			if full or is_backup.match(file.suffixes[-2]):
				self.log.info(f'Deleting {file}')
				if not dryrun:
					FileIO.delete(file)

	@cached
	def _cached_page_image(self, docid: str, page: int):
		Workspace.log.debug(f'_cached_page_image: {docid} page {page}')
		import fitz
		doc = fitz.open(str(self.docs[docid].originalFile))
		_page = doc[page]
		img_info = _page.getImageList()[0]
		xref = img_info[0]
		pix = fitz.Pixmap(doc, xref)
		return xref, _page.rect, pix


##########################################################################################


def _tokensaver(func):
	@functools.wraps(func)
	def wrapper(*args, **kwargs):
		Document.log.debug(f'args: {args}, kwargs: {kwargs}')
		def arg(name, index):
			if kwargs and name in kwargs:
				return kwargs[name]
			if len(args) > index:
				return args[index]
			return None
		self = args[0]
		force = arg('force', 3)
		kind = func.__name__
		if not force and TokenList.exists(self.workspace.storageconfig, self.docid, kind):
			Workspace.log.info(f'Storage containing {kind} for {self.docid} exists and will be returned as a TokenList. Use --force or delete it to rerun.')
			tl = TokenList.new(self.workspace.storageconfig)
			tl.load(self.docid, kind)
			Workspace.log.debug(f'Loaded {len(tl)} tokens.')
			return tl

		tokens = func(*args, **kwargs)

		if len(tokens) > 0:
			Workspace.log.info(f'Writing {kind} for {self.docid}')
			tokens.save(kind)

		return tokens
	return wrapper


class Document(object):
	log = logging.getLogger(f'{__name__}.Document')

	"""
	Documents provide access to paths and :class:`Tokens<CorrectOCR.tokens.Token>`.
	"""
	def __init__(self, workspace: Workspace, docid: str, ext: str, original: Path, gold: Path, training: Path, corrected: Path, nheaderlines: int = 0):
		"""
		:param docid: Base filename (ie. without extension).
		:param ext: The extension (including leading period).
		:param original: Directory for original uncorrected files.
		:param gold: Directory for known correct "gold" files (if any).
		:param training: Directory for storing intermediate files.
		:param corrected: Directory for saving corrected files.
		:param nheaderlines: Number of lines in file header (only relevant for ``.txt`` files)
		"""
		self.workspace = workspace
		self.docid = docid
		self.ext = ext
		if self.ext == '.txt':
			self.originalFile: Union[CorpusFile, Path] = CorpusFile(original.joinpath(f'{docid}{ext}'), nheaderlines)
			self.goldFile: Union[CorpusFile, Path] = CorpusFile(gold.joinpath(f'{docid}{ext}'), nheaderlines)
			self.correctedFile: Union[CorpusFile, Path] = CorpusFile(corrected.joinpath(f'{docid}{ext}'), nheaderlines)
		else:
			self.originalFile: Union[CorpusFile, Path] = original.joinpath(f'{docid}{ext}')
			self.goldFile: Union[CorpusFile, Path] = gold.joinpath(f'{docid}{ext}')
			self.correctedFile: Union[CorpusFile, Path] = corrected.joinpath(f'{docid}{ext}')
		self.originalTokenFile = training.joinpath(f'{docid}.tokens.csv')  #: Path to original token file (CSV format).
		self.alignedTokenFile = training.joinpath(f'{docid}.alignedTokens.csv')  #: Path to aligned token file (CSV format).
		self.kbestTokenFile = training.joinpath(f'{docid}.kbestTokens.csv')  #: Path to token file with *k*-best suggestions (CSV format).
		self.binnedTokenFile = training.joinpath(f'{docid}.binnedTokens.csv')  #: Path to token file with bins applied (CSV format).
		self.correctedTokenFile = training.joinpath(f'{docid}.correctedTokens.csv')  #: Path to token file with autocorrections applied (CSV format).
		self.fullAlignmentsFile = training.joinpath(f'{docid}.fullAlignments.json')  #: Path to full letter-by-letter alignments (JSON format).
		self.wordAlignmentsFile = training.joinpath(f'{docid}.wordAlignments.json')  #: Path to word-by-word alignments (JSON format).
		self.readCountsFile = training.joinpath(f'{docid}.readCounts.json')  #: Path to letter read counts (JSON format).

	def alignments(self, force=False) -> Tuple[list, dict, list]:
		"""
		Uses the :class:`Aligner<CorrectOCR.aligner.Aligner>` to generate alignments for a given
		original, gold pair of docs.

		Caches its results in the ``trainingPath``.

		:param force: Back up existing alignment docs and create new ones.
		"""
		faPath = self.fullAlignmentsFile
		waPath = self.wordAlignmentsFile
		mcPath = self.readCountsFile
		
		if not force and (faPath.is_file() and waPath.is_file() and mcPath.is_file()):
			Document.log.info(f'Alignments for {self.docid} exist and are presumed correct, will read and return. Use --force or delete alignments to rerun a subset.')
			return (
				FileIO.load(faPath),
				{o: {int(k): v for k, v in i.items()} for o, i in FileIO.load(waPath).items()},
				FileIO.load(mcPath)
			)
		Document.log.info(f'Creating alignments for {self.docid}')
		
		if self.originalFile.body == self.goldFile.body:
			Document.log.critical(f'Original and gold are identical for {self.docid}!')
			raise SystemExit(-1)
		
		(fullAlignments, wordAlignments, readCounts) = Aligner().alignments(
			tokenize_str(self.originalFile.body, self.workspace.config.language.name),
			tokenize_str(self.goldFile.body, self.workspace.config.language.name)
		)
		
		FileIO.save(fullAlignments, faPath)
		FileIO.save(wordAlignments, waPath)
		FileIO.save(readCounts, mcPath)

		#Workspace.log.debug(f'wordAlignments: {wordAlignments}')
		
		return fullAlignments, wordAlignments, readCounts

	@_tokensaver
	def tokens(self, k: int, dehyphenate=False, force=False) -> TokenList:
		"""
		Generate :class:`Tokens<CorrectOCR.tokens.Token>` for the given doc.

		Caches its results in the ``trainingPath``.

		:param k: Unused in this method, but may be used by internal call to :meth:`kbestTokens()<CorrectOCR.workspace.Document.kbestTokens>`.
		:param dehyphenate: Whether to attempt dehyphenization of tokens.
		:param force: Back up existing tokens and create new ones.
		"""
		
		Document.log.info(f'Creating basic tokens for {self.docid}')
		tokenizer = Tokenizer.for_extension(self.ext)(self.workspace.config.language, dehyphenate)
		tokens = tokenizer.tokenize(
			self.originalFile,
			self.workspace.storageconfig
		)
		
		return tokens

	@_tokensaver
	def alignedTokens(self, k: int, dehyphenate=False, force=False) -> TokenList:
		"""
		If possible, uses the ``alignments`` to add gold alignments to the generated tokens.

		Caches its results in the ``trainingPath``.

		:param k: Unused in this method, but may be used by internal call to :meth:`kbestTokens()<CorrectOCR.workspace.Document.kbestTokens>`.
		:param dehyphenate: Whether to attempt dehyphenization of tokens.
		:param force: Back up existing tokens and create new ones.
		"""
		tokens = self.tokens(k, dehyphenate, force)

		Document.log.info(f'Creating aligned tokens for {self.docid}')
		if self.goldFile.is_file():
			(_, wordAlignments, _) = self.alignments()
			for i, token in enumerate(tokens):
				if not token.gold and token.original in wordAlignments:
					wa = wordAlignments[token].items()
					closest = sorted(wa, key=lambda x: abs(x[0]-i))
					#Document.log.debug(f'{wa} {i} {token.original} {closest}')
					token.gold = closest[0][1]

			return tokens
		return TokenList.new(self.storageconfig)

	@_tokensaver
	def kbestTokens(self, k: int, dehyphenate=False, force=False) -> TokenList:
		"""
		Uses the :class:`HMM<CorrectOCR.model.HMM>` to add *k*-best suggestions to the generated tokens.

		Caches its results in the ``trainingPath``.

		:param k: How many `k` to calculate.
		:param dehyphenate: Whether to attempt dehyphenization of tokens.
		:param force: Back up existing tokens and create new ones.
		"""
		if self.goldFile.is_file():
			tokens = self.alignedTokens(k, dehyphenate, force)
		else:
			tokens = self.tokens(k, dehyphenate, force)

		Document.log.info(f'Creating k-best tokens for {self.docid}')
		self.workspace.resources.hmm.generate_kbest(tokens, k)

		return tokens

	@_tokensaver
	def binnedTokens(self, k: int, dehyphenate=False, force=False) -> TokenList:
		"""
		Uses the :class:`Heuristics<CorrectOCR.heuristics.Heuristics>` to decide whether human or
		automatic corrections are appropriate for the generated tokens.

		Caches its results in the ``trainingPath``.

		:param k: Unused in this method, but may be used by internal call to :meth:`kbestTokens()<CorrectOCR.workspace.Document.kbestTokens>`.
		:param dehyphenate: Whether to attempt dehyphenization of tokens.
		:param force: Back up existing tokens and create new ones.
		"""
		tokens = self.kbestTokens(k, dehyphenate, force)

		Document.log.info(f'Creating binned tokens for {self.docid}')
		self.workspace.resources.heuristics.bin_tokens(tokens)

		return tokens

	@_tokensaver
	def autocorrectedTokens(self, k: int, dehyphenate=False, force=False) -> TokenList:
		"""
		Applies the suggested corrections and leaves those marked 'annotator'
		for human annotation.

		:param k: Unused in this method, but may be used by internal call to :meth:`kbestTokens()<CorrectOCR.workspace.Document.kbestTokens>`.
		:param dehyphenate: Whether to attempt dehyphenization of tokens.
		:param force: Back up existing tokens and create new ones.
		"""
		tokens = self.binnedTokens(k, dehyphenate, force)
		
		for t in tokens:
			if t.decision in {'kbest', 'kdict'}:
				t.gold = t.kbest[int(t.selection)].candidate
			elif t.decision == 'original':
				t.gold = t.original

		return tokens



class CorpusFile(object):
	"""
	Simple wrapper for text files to manage a number of lines as a separate header.
	"""
	log = logging.getLogger(f'{__name__}.CorpusFile')

	def __init__(self, path: Path, nheaderlines: int = 0):
		"""
		:param path: Path to text file.
		:param nheaderlines: Number of lines from beginning to separate out as header.
		"""
		self.path = path
		self.nheaderlines = nheaderlines
		if self.path.is_file():
			lines = FileIO.load(self.path).split('\n')
			(self.header, self.body) = (
				str.join('', lines[:self.nheaderlines-1]),
				str.join('', lines[nheaderlines:])
			)
		else:
			(self.header, self.body) = ('', '')

	def save(self):
		"""
		Concatenate header and body and save.
		"""
		if not self.header or self.header.strip() == '':
			self.header = ''
		elif self.header[-1] != '\n':
			self.header += '\n'
		CorpusFile.log.info(f'Saving file to {self.path}')
		FileIO.save(self.header + self.body, self.path)

	def is_file(self) -> bool:
		"""
		:return: Does the file exist? See :meth:`pathlib.Path.is_file`.
		"""
		return self.path.is_file()

	@property
	def id(self):
		return self.path.stem


##########################################################################################


class JSONResource(dict):
	"""
	Simple wrapper for JSON files.
	"""
	log = logging.getLogger(f'{__name__}.JSONResource')

	def __init__(self, path, **kwargs):
		"""
		:param path: Path to load from.
		:param kwargs: TODO
		"""
		super().__init__(**kwargs)
		JSONResource.log.info(f'Loading {path}')
		self._path = path
		data = FileIO.load(self._path, default=dict())
		if data:
			self.update(data)

	def save(self):
		"""
		Save to JSON file.
		"""
		FileIO.save(self, self._path)

	def __repr__(self):
		return f'<JSONResource {self._path}: {dict(self)}>'


##########################################################################################


class ResourceManager(object):
	"""
	Helper for the Workspace to manage various resources.
	"""
	log = logging.getLogger(f'{__name__}.ResourceManager')

	def __init__(self, root: Path, config):
		"""
		:param root: Path to resources directory.
		:param config: An object with the following properties:

		   -  **correctionTrackingFile** (:class:`Path<pathlib.Path>`): Path to file containing correction tracking.
		   -  TODO
		"""
		self.root = root.joinpath(config.resourceRootPath).resolve()
		ResourceManager.log.info(f'ResourceManager configuration:\n{pformat(vars(config))} at {self.root}')
		self.correctionTracking = JSONResource(self.root.joinpath(config.correctionTrackingFile).resolve())
		self.memoizedCorrections = JSONResource(self.root.joinpath(config.memoizedCorrectionsFile).resolve())
		self.multiCharacterError = JSONResource(self.root.joinpath(config.multiCharacterErrorFile).resolve())
		self.dictionary = Dictionary(self.root.joinpath(config.dictionaryFile).resolve(), config.ignoreCase)
		self.hmm = HMM(self.root.joinpath(config.hmmParamsFile).resolve(), self.multiCharacterError, self.dictionary)
		self.reportFile = self.root.joinpath(config.reportFile).resolve()
		self.heuristics = Heuristics(JSONResource(self.root.joinpath(config.heuristicSettingsFile).resolve()), self.dictionary)

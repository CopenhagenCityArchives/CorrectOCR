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
from .tokens import Token, Tokenizer, TokenList, tokenize_str, dehyphenate_tokens


def _tokensaver(func):
	@functools.wraps(func)
	def wrapper(*args, **kwargs):
		#Workspace.log.debug(f'args: {args}, kwargs: {kwargs}')
		def arg(name, index):
			if kwargs and name in kwargs:
				return kwargs[name]
			if len(args) > index:
				return args[index]
			return None
		self = args[0]
		fileid = arg('fileid', 1)
		force = arg('force', 4)
		kind = func.__name__
		if not force and TokenList.exists(self.storageconfig, fileid, kind):
			Workspace.log.info(f'Storage containing {kind} for {fileid} exists and will be returned as a TokenList. Use --force or delete it to rerun.')
			tl = TokenList.new(self.storageconfig)
			tl.load(fileid, kind)
			Workspace.log.debug(f'Loaded {len(tl)} tokens.')
			return tl

		tokens = func(*args, **kwargs)

		if len(tokens) > 0:
			Workspace.log.info(f'Writing {kind} for {fileid}')
			tokens.save(kind)

		return tokens
	return wrapper


class Workspace(object):
	"""
	The Workspace holds references to paths and resources used by the various :mod:`commands<CorrectOCR.commands>`.

	Additionally, it is responsible for generating intermediate files for :class:`Tokens<CorrectOCR.tokens.Token>`.

	:param workspaceconfig: An object with the following properties:

	   -  **nheaderlines** (:class:`int`): The number of header lines in corpus texts.
	   -  **language**: A language instance from `pycountry <https://pypi.org/project/pycountry/>`.
	   -  **originalPath** (:class:`Path<pathlib.Path>`): Directory containing the original files.
	   -  **goldPath** (:class:`Path<pathlib.Path>`): Directory containing the gold (if any) files.
	   -  **trainingPath** (:class:`Path<pathlib.Path>`): Directory for storing intermediate files.
	   -  **correctedPath** (:class:`Path<pathlib.Path>`): Directory for saving corrected files.

	:param resourceconfig: Passed directly to :class:`ResourceManager<CorrectOCR.workspace.ResourceManager>`, see this for further info.
	"""
	log = logging.getLogger(f'{__name__}.Workspace')

	def __init__(self, workspaceconfig, resourceconfig, storageconfig):
		self.root = workspaceconfig.rootPath.resolve()
		Workspace.log.info(f'Workspace configuration:\n{pformat(vars(workspaceconfig))} at {self.root}')
		Workspace.log.info(f'Storage configuration:\n{pformat(vars(storageconfig))}')
		self.storageconfig = storageconfig
		self.nheaderlines: int = workspaceconfig.nheaderlines
		self.language = workspaceconfig.language
		self.resources = ResourceManager(self.root, resourceconfig)
		self.paths: Dict[str, PathManager] = dict()
		self._originalPath = self.root.joinpath(workspaceconfig.originalPath).resolve()
		self._goldPath = self.root.joinpath(workspaceconfig.goldPath).resolve()
		self._trainingPath = self.root.joinpath(workspaceconfig.trainingPath).resolve()
		self._correctedPath = self.root.joinpath(workspaceconfig.correctedPath).resolve()
		for file in workspaceconfig.originalPath.iterdir():
			if file.name in {'.DS_Store'}:
				continue
			self.add_fileid(file.stem, file.suffix)
		self.cache = LRUCache(maxsize=1000)
		self.cachePath = FileIO.cachePath

	def add_fileid(self, fileid: str, ext: str, new_original: Path = None):
		"""
		Initializes a new :class:`PathManager` with the ``fileid`` and adds it to the
		workspace.

		:param fileid: The fileid (filename without extension).
		:param ext: The extension, including leading period.
		:param new_original: Path to a new file that should be copied to the generated `originalPath`.
		"""
		if new_original:
			FileIO.copy(new_original, self._originalPath)
		self.paths[fileid] = PathManager(
			fileid,
			ext,
			self._originalPath,
			self._goldPath,
			self._trainingPath,
			self._correctedPath,
			self.nheaderlines,
		)

	def originalTokens(self) -> Iterator[Tuple[str, TokenList]]:
		"""
		Yields an iterator of (fileid, list of tokens).
		"""
		for fileid, pathManager in self.paths.items():
			if pathManager.originalTokenFile.is_file():
				Workspace.log.debug(f'Getting original tokens from {fileid}')
				yield fileid, [Token.from_dict(row) for row in FileIO.load(pathManager.originalTokenFile)]

	def goldTokens(self) -> Iterator[Tuple[str, TokenList]]:
		"""
		Yields an iterator of (fileid, list of gold-aligned tokens).
		"""
		for fileid, pathManager in self.paths.items():
			if pathManager.alignedTokenFile.is_file():
				Workspace.log.debug(f'Getting gold tokens from {fileid}')
				yield fileid, [Token.from_dict(row) for row in FileIO.load(pathManager.alignedTokenFile)]

	def alignments(self, fileid: str, force=False) -> Tuple[list, dict, list]:
		"""
		Uses the :class:`Aligner<CorrectOCR.aligner.Aligner>` to generate alignments for a given
		original, gold pair of files.

		Caches its results in the ``trainingPath``.

		:param fileid: ID of the file pair for which to generate alignments.
		:param force: Back up existing alignment files and create new ones.
		"""
		faPath = self.paths[fileid].fullAlignmentsFile
		waPath = self.paths[fileid].wordAlignmentsFile
		mcPath = self.paths[fileid].readCountsFile
		
		if not force and (faPath.is_file() and waPath.is_file() and mcPath.is_file()):
			# presume correctness, user may clean the files to rerun
			Workspace.log.info(f'Alignment files for {fileid} exist, will read and return. Use --force or clean files to rerun a subset.')
			return (
				FileIO.load(faPath),
				{o: {int(k): v for k, v in i.items()} for o, i in FileIO.load(waPath).items()},
				FileIO.load(mcPath)
			)
		Workspace.log.info(f'Creating alignment files for {fileid}')
		
		if self.paths[fileid].originalFile.body == self.paths[fileid].goldFile.body:
			Workspace.log.critical(f'Original and gold are identical for {fileid}!')
			raise SystemExit(-1)
		
		(fullAlignments, wordAlignments, readCounts) = Aligner().alignments(
			tokenize_str(self.paths[fileid].originalFile.body, self.language.name),
			tokenize_str(self.paths[fileid].goldFile.body, self.language.name)
		)
		
		FileIO.save(fullAlignments, faPath)
		FileIO.save(wordAlignments, waPath)
		FileIO.save(readCounts, mcPath)

		#Workspace.log.debug(f'wordAlignments: {wordAlignments}')
		
		return fullAlignments, wordAlignments, readCounts

	@_tokensaver
	def tokens(self, fileid: str, k: int, dehyphenate=False, force=False) -> TokenList:
		"""
		Generate :class:`Tokens<CorrectOCR.tokens.Token>` for the given file.

		Caches its results in the ``trainingPath``.

		:param fileid: ID of the file for which to generate tokens.
		:param k: Unused in this method.
		:param dehyphenate: Whether to attempt dehyphenization of tokens.
		:param force: Back up existing token file and create a new one.
		"""
		Workspace.log.info(f'Creating basic tokens for {fileid}')
		tokenizer = Tokenizer.for_extension(self.paths[fileid].ext)(self.language)
		tokens = tokenizer.tokenize(
			self.paths[fileid].originalFile,
			self.storageconfig
		)

		if dehyphenate:
			tokens = dehyphenate_tokens(tokens)
		
		return tokens

	@_tokensaver
	def alignedTokens(self, fileid: str, k: int, dehyphenate=False, force=False) -> TokenList:
		"""
		If possible, uses the ``alignments`` to add gold alignments to the generated tokens.

		Caches its results in the ``trainingPath``.

		:param fileid: ID of the file for which to generate tokens.
		:param k: Unused in this method.
		:param dehyphenate: Whether to attempt dehyphenization of tokens.
		:param force: Back up existing token file and create a new one.
		"""
		tokens = self.tokens(fileid, k, dehyphenate, force)

		Workspace.log.info(f'Creating aligned tokens for {fileid}')
		if self.paths[fileid].goldFile.is_file():
			(_, wordAlignments, _) = self.alignments(fileid)
			for i, token in enumerate(tokens):
				if not token.gold and token.original in wordAlignments:
					wa = wordAlignments[token].items()
					closest = sorted(wa, key=lambda x: abs(x[0]-i))
					#Workspace.log.debug(f'{wa} {i} {token.original} {closest}')
					token.gold = closest[0][1]

			return tokens
		return TokenList.new(self.storageconfig)

	@_tokensaver
	def kbestTokens(self, fileid: str, k: int, dehyphenate=False, force=False) -> TokenList:
		"""
		Uses the :class:`HMM<CorrectOCR.model.HMM>` to add *k*-best suggestions to the generated tokens.

		Caches its results in the ``trainingPath``.

		:param fileid: ID of the file for which to generate tokens.
		:param k: Unused in this method.
		:param dehyphenate: Whether to attempt dehyphenization of tokens.
		:param force: Back up existing token file and create a new one.
		"""
		if self.paths[fileid].goldFile.is_file():
			tokens = self.alignedTokens(fileid, k, dehyphenate, force)
		else:
			tokens = self.tokens(fileid, k, dehyphenate, force)

		Workspace.log.info(f'Creating k-best tokens for {fileid}')
		self.resources.hmm.generate_kbest(tokens, k)

		return tokens

	@_tokensaver
	def binnedTokens(self, fileid: str, k: int, dehyphenate=False, force=False) -> TokenList:
		"""
		Uses the :class:`Heuristics<CorrectOCR.heuristics.Heuristics>` to decide whether human or
		automatic corrections are appropriate for the generated tokens.

		Caches its results in the ``trainingPath``.

		:param fileid: ID of the file for which to generate tokens.
		:param k: Unused in this method.
		:param dehyphenate: Whether to attempt dehyphenization of tokens.
		:param force: Back up existing token file and create a new one.
		"""
		tokens = self.kbestTokens(fileid, k, dehyphenate, force)

		Workspace.log.info(f'Creating binned tokens for {fileid}')
		self.resources.heuristics.bin_tokens(tokens)

		return tokens

	@_tokensaver
	def autocorrectedTokens(self, fileid: str, k: int, dehyphenate=False, force=False) -> TokenList:
		"""
		Applies the suggested corrections and leaves those marked 'annotator'
		for human annotation.

		:param fileid: ID of the file for which to generate tokens.
		:param k: Unused in this method.
		:param dehyphenate: Whether to attempt dehyphenization of tokens.
		:param force: Back up existing token file and create a new one.
		"""
		tokens = self.binnedTokens(fileid, k, dehyphenate, force)
		
		for t in tokens:
			if t.decision in {'kbest', 'kdict'}:
				t.gold = t.kbest[int(t.selection)].candidate
			elif t.decision == 'original':
				t.gold = t.original

		return tokens

	def cleanup(self, dryrun=True, full=False):
		"""
		Cleans up the backup files in the ``trainingPath``.

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
	def _cached_page_image(self, fileid: str, page: int):
		Workspace.log.debug(f'_cached_page_image: {fileid} page {page}')
		import fitz
		doc = fitz.open(str(self.paths[fileid].originalFile))
		_page = doc[page]
		img_info = _page.getImageList()[0]
		xref = img_info[0]
		pix = fitz.Pixmap(doc, xref)
		return xref, _page.rect, pix


##########################################################################################


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


class PathManager(object):
	"""
	Helper for the Workspace that generates all the necessary paths to permanent and temporary
	files.
	"""
	def __init__(self, fileid: str, ext: str, original: Path, gold: Path, training: Path, corrected: Path, nheaderlines: int = 0):
		"""
		:param fileid: Base filename (ie. without extension).
		:param ext: The extension (including leading period).
		:param original: Directory for original uncorrected files.
		:param gold: Directory for known correct “gold” files (if any).
		:param training: Directory for storing intermediate files.
		:param corrected: Directory for saving corrected files.
		:param nheaderlines: Number of lines in file header (only relevant for ``.txt`` files)
		"""
		self.ext = ext
		if self.ext == '.txt':
			self.originalFile: Union[CorpusFile, Path] = CorpusFile(original.joinpath(f'{fileid}{ext}'), nheaderlines)
			self.goldFile: Union[CorpusFile, Path] = CorpusFile(gold.joinpath(f'{fileid}{ext}'), nheaderlines)
			self.correctedFile: Union[CorpusFile, Path] = CorpusFile(corrected.joinpath(f'{fileid}{ext}'), nheaderlines)
		else:
			self.originalFile: Union[CorpusFile, Path] = original.joinpath(f'{fileid}{ext}')
			self.goldFile: Union[CorpusFile, Path] = gold.joinpath(f'{fileid}{ext}')
			self.correctedFile: Union[CorpusFile, Path] = corrected.joinpath(f'{fileid}{ext}')
		self.originalTokenFile = training.joinpath(f'{fileid}.tokens.csv')  #: Path to original token file (CSV format).
		self.alignedTokenFile = training.joinpath(f'{fileid}.alignedTokens.csv')  #: Path to aligned token file (CSV format).
		self.kbestTokenFile = training.joinpath(f'{fileid}.kbestTokens.csv')  #: Path to token file with *k*-best suggestions (CSV format).
		self.binnedTokenFile = training.joinpath(f'{fileid}.binnedTokens.csv')  #: Path to token file with bins applied (CSV format).
		self.correctedTokenFile = training.joinpath(f'{fileid}.correctedTokens.csv')  #: Path to token file with autocorrections applied (CSV format).
		self.fullAlignmentsFile = training.joinpath(f'{fileid}.fullAlignments.json')  #: Path to full letter-by-letter alignments (JSON format).
		self.wordAlignmentsFile = training.joinpath(f'{fileid}.wordAlignments.json')  #: Path to word-by-word alignments (JSON format).
		self.readCountsFile = training.joinpath(f'{fileid}.readCounts.json')  #: Path to letter read counts (JSON format).


##########################################################################################


class ResourceManager(object):
	"""
	Helper for the Workspace to manage various resources.
	"""
	log = logging.getLogger(f'{__name__}.ResourceManager')

	def __init__(self, root: Path, config):
		"""
		:param root: Path to resources directory.
		:param config: TODO
		"""
		self.root = root.joinpath(config.resourceRootPath).resolve()
		ResourceManager.log.info(f'ResourceManager configuration:\n{pformat(vars(config))} at {self.root}')
		self.correctionTracking = JSONResource(self.root.joinpath(config.correctionTrackingFile).resolve())
		self.memoizedCorrections = JSONResource(self.root.joinpath(config.memoizedCorrectionsFile).resolve())
		self.multiCharacterError = JSONResource(self.root.joinpath(config.multiCharacterErrorFile).resolve())
		self.dictionary = Dictionary(self.root.joinpath(config.dictionaryFile).resolve(), config.caseInsensitive)
		self.hmm = HMM(self.root.joinpath(config.hmmParamsFile).resolve(), self.multiCharacterError, self.dictionary)
		self.reportFile = self.root.joinpath(config.reportFile).resolve()
		self.heuristics = Heuristics(JSONResource(self.root.joinpath(config.heuristicSettingsFile).resolve()), self.dictionary)

from __future__ import annotations

import functools
import logging
import re
from pathlib import Path
from pprint import pformat
from typing import Dict, Iterator, List, Tuple, Union

from ._cache import LRUCache, cached
from .aligner import Aligner
from .dictionary import Dictionary
from .fileio import FileIO
from .heuristics import Heuristics
from .model import HMM
from .tokens import Token, Tokenizer, tokenize_str, dehyphenate_tokens


def _tokensaver(get_path):
	def decorator(func):
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
			path = get_path(self.paths[fileid])
			if not force and path.is_file():
				Workspace.log.info(f'File containing {func.__name__} for {fileid} exists and will be returned as Token objects. Use --force or delete it to rerun.')
				return [Token.from_dict(row) for row in FileIO.load(path)]

			tokens = func(*args, **kwargs)

			if len(tokens) > 0:
				Workspace.log.info(f'Writing tokens to {path}')
				FileIO.save(tokens, path)

			return tokens
		return wrapper
	return decorator


class Workspace(object):
	"""
	The Workspace holds references to paths and resources used by the various :mod:`commands<CorrectOCR.commands>`.

	Additionally, it is responsible for generating intermediate files for :class:`Tokens<CorrectOCR.tokens.Token>`.

	:param workspaceconfig: An object with the following properties:

	   -  `nheaderlines`: The number of header lines in corpus texts.
	   -  `language`: A language instance from `pycountry <https://pypi.org/project/pycountry/>`.
	   -  `originalPath`: A :class:`pathlib.Path` to a directory containing the original files.
	   -  `goldPath`: A :class:`pathlib.Path` to a directory containing the gold (if any) files.
	   -  `trainingPath`: A :class:`pathlib.Path` to a directory for saving intermediate files.
	   -  `correctedPath`: A :class:`pathlib.Path` to a directory for saving corrected files.

	:param resourceconfig: An object TODO
	"""
	log = logging.getLogger(f'{__name__}.Workspace')

	def __init__(self, workspaceconfig, resourceconfig):
		self.root = workspaceconfig.rootPath.resolve()
		Workspace.log.info(f'Workspace configuration:\n{pformat(vars(workspaceconfig))} at {self.root}')
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
		self.cachePath = FileIO._cachePath

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

	def originalTokens(self) -> Iterator[Tuple[str, List[Token]]]:
		"""
		Yields an iterator of (fileid, list of tokens).
		"""
		for fileid, pathManager in self.paths.items():
			if pathManager.originalTokenFile.is_file():
				Workspace.log.debug(f'Getting original tokens from {fileid}')
				yield fileid, [Token.from_dict(row) for row in FileIO.load(pathManager.originalTokenFile)]

	def goldTokens(self) -> Iterator[Tuple[str, List[Token]]]:
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

	@_tokensaver(lambda p: p.originalTokenFile)
	def tokens(self, fileid: str, k: int, dehyphenate=False, force=False) -> List[Token]:
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
		)

		if dehyphenate:
			tokens = dehyphenate_tokens(tokens)
		
		return tokens

	@_tokensaver(lambda p: p.alignedTokenFile)
	def alignedTokens(self, fileid: str, k: int, dehyphenate=False, force=False) -> List[Token]:
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
		return []

	@_tokensaver(lambda p: p.kbestTokenFile)
	def kbestTokens(self, fileid: str, k: int, dehyphenate=False, force=False) -> List[Token]:
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

	@_tokensaver(lambda p: p.binnedTokenFile)
	def binnedTokens(self, fileid: str, k: int, dehyphenate=False, force=False) -> List[Token]:
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

	def autocorrectedTokens(self, fileid: str, k: int, dehyphenate=False, force=False) -> List[Token]:
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
	log = logging.getLogger(f'{__name__}.CorpusFile')

	def __init__(self, path, nheaderlines=0):
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
		if not self.header or self.header.strip() == '':
			self.header = ''
		elif self.header[-1] != '\n':
			self.header += '\n'
		CorpusFile.log.info(f'Saving file to {self.path}')
		FileIO.save(self.header + self.body, self.path)

	def is_file(self):
		return self.path.is_file()


##########################################################################################


class JSONResource(dict):
	log = logging.getLogger(f'{__name__}.JSONResource')

	def __init__(self, path, **kwargs):
		super().__init__(**kwargs)
		JSONResource.log.info(f'Loading {path}')
		self._path = path
		data = FileIO.load(self._path, default=dict())
		if data:
			self.update(data)

	def save(self):
		FileIO.save(self, self._path)

	def __repr__(self):
		return f'<JSONResource {self._path}: {dict(self)}>'


##########################################################################################


class PathManager(object):
	def __init__(self, fileid: str, ext: str, original: Path, gold: Path, training: Path, corrected: Path, nheaderlines: int = 0):
		self.ext = ext
		if self.ext == '.txt':
			self.originalFile: Union[CorpusFile, Path] = CorpusFile(original.joinpath(f'{fileid}{ext}'), nheaderlines)
			self.goldFile: Union[CorpusFile, Path] = CorpusFile(gold.joinpath(f'{fileid}{ext}'), nheaderlines)
			self.correctedFile: Union[CorpusFile, Path] = CorpusFile(corrected.joinpath(f'{fileid}{ext}'), nheaderlines)
		else:
			self.originalFile: Union[CorpusFile, Path] = original.joinpath(f'{fileid}{ext}')
			self.goldFile: Union[CorpusFile, Path] = gold.joinpath(f'{fileid}{ext}')
			self.correctedFile: Union[CorpusFile, Path] = corrected.joinpath(f'{fileid}{ext}')
		self.originalTokenFile = training.joinpath(f'{fileid}.tokens.csv')
		self.alignedTokenFile = training.joinpath(f'{fileid}.alignedTokens.csv')
		self.kbestTokenFile = training.joinpath(f'{fileid}.kbestTokens.csv')
		self.binnedTokenFile = training.joinpath(f'{fileid}.binnedTokens.csv')
		self.correctedTokenFile = training.joinpath(f'{fileid}.correctedTokens.csv')
		self.fullAlignmentsFile = training.joinpath(f'{fileid}.fullAlignments.json')
		self.wordAlignmentsFile = training.joinpath(f'{fileid}.wordAlignments.json')
		self.readCountsFile = training.joinpath(f'{fileid}.readCounts.json')


##########################################################################################


class ResourceManager(object):
	log = logging.getLogger(f'{__name__}.ResourceManager')

	def __init__(self, root, config):
		self.root = root.joinpath(config.resourceRootPath).resolve()
		ResourceManager.log.info(f'ResourceManager configuration:\n{pformat(vars(config))} at {self.root}')
		self.correctionTracking = JSONResource(self.root.joinpath(config.correctionTrackingFile).resolve())
		self.memoizedCorrections = JSONResource(self.root.joinpath(config.memoizedCorrectionsFile).resolve())
		self.multiCharacterError = JSONResource(self.root.joinpath(config.multiCharacterErrorFile).resolve())
		self.dictionary = Dictionary(self.root.joinpath(config.dictionaryFile).resolve(), config.caseInsensitive)
		self.hmm = HMM(self.root.joinpath(config.hmmParamsFile).resolve(), self.multiCharacterError, self.dictionary)
		self.reportFile = self.root.joinpath(config.reportFile).resolve()
		self.heuristics = Heuristics(JSONResource(self.root.joinpath(config.heuristicSettingsFile).resolve()), self.dictionary)

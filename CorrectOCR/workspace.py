import functools
import logging
from pathlib import Path
from pprint import pformat
from typing import Dict, Iterator, List, Tuple, Union

from .aligner import Aligner
from .dictionary import Dictionary
from .fileio import FileIO
from .heuristics import Heuristics
from .model import HMM
from .tokens import Token, Tokenizer, tokenize_str, dehyphenate_tokens


def tokensaver(get_path):
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

			Workspace.log.info(f'Writing tokens to {path}')
			FileIO.save(tokens, path)

			return tokens
		return wrapper
	return decorator


class Workspace(object):
	log = logging.getLogger(f'{__name__}.Workspace')

	def __init__(self, workspaceconfig, resourceconfig):
		Workspace.log.info(f'Workspace configuration:\n{pformat(vars(workspaceconfig))}')
		self.nheaderlines: int = workspaceconfig.nheaderlines
		self.language = workspaceconfig.language
		self.resources = ResourceManager(resourceconfig)
		self.paths: Dict[str, PathManager] = dict()
		self._originalPath = workspaceconfig.originalPath
		self._goldPath = workspaceconfig.goldPath
		self._trainingPath = workspaceconfig.trainingPath
		self._correctedPath = workspaceconfig.correctedPath
		self._nheaderlines = workspaceconfig.nheaderlines
		for file in workspaceconfig.originalPath.iterdir():
			if file.name in {'.DS_Store'}:
				continue
			self.add_new_path(file.stem, file.suffix)

	def add_new_path(self, fileid, ext, new_original: Path = None):
		if new_original:
			FileIO.copy(new_original, self._originalPath)
		self.paths[fileid] = PathManager(
			fileid,
			ext,
			self._originalPath,
			self._goldPath,
			self._trainingPath,
			self._correctedPath,
			self._nheaderlines,
		)

	def originalTokens(self) -> Iterator[Tuple[str, List[Token]]]:
		for fileid, pathManager in self.paths.items():
			if pathManager.originalTokenFile.is_file():
				Workspace.log.debug(f'Getting original tokens from {fileid}')
				yield fileid, [Token.from_dict(row) for row in FileIO.load(pathManager.originalTokenFile)]

	def goldTokens(self) -> Iterator[Tuple[str, List[Token]]]:
		for fileid, pathManager in self.paths.items():
			if pathManager.alignedTokenFile.is_file():
				Workspace.log.debug(f'Getting gold tokens from {fileid}')
				yield fileid, [Token.from_dict(row) for row in FileIO.load(pathManager.alignedTokenFile)]

	def alignments(self, fileid: str, force=False) -> Tuple[list, dict, list]:
		faPath = self.paths[fileid].fullAlignmentsFile
		waPath = self.paths[fileid].wordAlignmentsFile
		mcPath = self.paths[fileid].misreadCountsFile
		
		if not force and (faPath.is_file() and waPath.is_file() and mcPath.is_file()):
			# presume correctness, user may clean the files to rerun
			Workspace.log.info(f'Alignment files for {fileid} exist, will read and return. Use --force or clean files to rerun a subset.')
			return (
				FileIO.load(faPath),
				{o: {int(k): v for k, v in i.items()} for o, i in FileIO.load(waPath).items()},
				FileIO.load(mcPath)
			)
		Workspace.log.info(f'Creating alignment files for {fileid}')
		
		(fullAlignments, wordAlignments, misreadCounts) = Aligner().alignments(
			tokenize_str(self.paths[fileid].originalFile.body, self.language.name),
			tokenize_str(self.paths[fileid].goldFile.body, self.language.name)
		)
		
		FileIO.save(fullAlignments, faPath)
		FileIO.save(wordAlignments, waPath)
		FileIO.save(misreadCounts, mcPath)

		#Workspace.log.debug(f'wordAlignments: {wordAlignments}')
		
		return fullAlignments, wordAlignments, misreadCounts

	@tokensaver(lambda p: p.originalTokenFile)
	def tokens(self, fileid: str, k: int, dehyphenate=False, force=False):
		Workspace.log.info(f'Creating basic tokens for {fileid}')
		tokenizer = Tokenizer.for_extension(self.paths[fileid].ext)(self.language)
		tokens = tokenizer.tokenize(
			self.paths[fileid].originalFile
		)

		if dehyphenate:
			tokens = dehyphenate_tokens(tokens)
		
		return tokens

	@tokensaver(lambda p: p.alignedTokenFile)
	def alignedTokens(self, fileid: str, k: int, dehyphenate=False, force=False):
		tokens = self.tokens(fileid, k, dehyphenate, force)

		Workspace.log.info(f'Creating aligned tokens for {fileid}')
		if self.paths[fileid].goldFile.is_file():
			(_, wordAlignments, _) = self.alignments(fileid)
			for i, token in enumerate(tokens):
				if not token.gold and token.original in wordAlignments:
					wa = wordAlignments[token].items()
					closest = sorted(wa, key=lambda x: abs(x[0]-i))
					Workspace.log.debug(f'{wa} {i} {token.original} {closest}')
					token.gold = closest[0][1]

		return tokens

	@tokensaver(lambda p: p.kbestTokenFile)
	def kbestTokens(self, fileid: str, k: int, dehyphenate=False, force=False):
		tokens = self.alignedTokens(fileid, k, dehyphenate, force)

		Workspace.log.info(f'Creating k-best tokens for {fileid}')
		self.resources.hmm.generate_kbest(tokens, k)

		return tokens

	@tokensaver(lambda p: p.binnedTokenFile)
	def binnedTokens(self, fileid: str, k: int, dehyphenate=False, force=False):
		tokens = self.kbestTokens(fileid, k, dehyphenate, force)

		Workspace.log.info(f'Creating binned tokens for {fileid}')
		self.resources.heuristics.bin_tokens(tokens)

		return tokens


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
		self.fullAlignmentsFile = training.joinpath(f'{fileid}.fullAlignments.json')
		self.wordAlignmentsFile = training.joinpath(f'{fileid}.wordAlignments.json')
		self.misreadCountsFile = training.joinpath(f'{fileid}.misreadCounts.json')


##########################################################################################


class ResourceManager(object):
	log = logging.getLogger(f'{__name__}.ResourceManager')

	def __init__(self, config):
		ResourceManager.log.info(f'ResourceManager configuration:\n{pformat(vars(config))}')
		self.correctionTracking = JSONResource(config.correctionTrackingFile)
		self.memoizedCorrections = JSONResource(config.memoizedCorrectionsFile)
		self.multiCharacterError = JSONResource(config.multiCharacterErrorFile)
		self.dictionary = Dictionary(config.dictionaryFile, config.caseInsensitive)
		self.hmm = HMM(config.hmmParamsFile, self.multiCharacterError, self.dictionary)
		self.reportFile = config.reportFile
		self.heuristics = Heuristics(JSONResource(config.heuristicSettingsFile), self.dictionary)

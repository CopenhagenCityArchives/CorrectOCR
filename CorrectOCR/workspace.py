import logging
from pathlib import Path
from pprint import pformat
from typing import Dict, Iterator, List, Tuple

from .aligner import Aligner
from .dictionary import Dictionary
from .fileio import FileIO
from .heuristics import Heuristics
from .model import HMM
from .tokenize import Token, Tokenizer, tokenize_str, dehyphenate_tokens


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
			if pathManager.goldTokenFile.is_file():
				Workspace.log.debug(f'Getting gold tokens from {fileid}')
				yield fileid, [Token.from_dict(row) for row in FileIO.load(pathManager.goldTokenFile)]

	def alignments(self, fileid: str, force=False) -> Tuple[list, dict, list]:
		faPath = self.paths[fileid].fullAlignmentsFile
		waPath = self.paths[fileid].wordAlignmentsFile
		mcPath = self.paths[fileid].misreadCountsFile
		
		if not force and (faPath.is_file() and waPath.is_file() and mcPath.is_file()):
			# presume correctness, user may clean the files to rerun
			Workspace.log.info(f'Alignment files for {fileid} exist, will read and return. Use --force or clean files to rerun a subset.')
			return (
				FileIO.load(faPath),
				{o: {int(k): v for k,v in i.items()} for o, i in FileIO.load(waPath).items()},
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

	def tokens(self, fileid: str, k=4, dehyphenate=False, getPreviousTokens=True, force=False):
		tokenFilePath = self.paths[fileid].originalTokenFile

		if not force and tokenFilePath.is_file():
			Workspace.log.info(f'{tokenFilePath} exists and will be returned as Token objects. Use --force or delete it to rerun.')
			return [Token.from_dict(row) for row in FileIO.load(tokenFilePath)]
		Workspace.log.info(f'Creating token files for {fileid}')
	
		# Load previously done tokens if any
		previousTokens: Dict[str, Token] = dict()
		if getPreviousTokens and not force:
			for fid, tokens in self.originalTokens():
				Workspace.log.debug(f'Getting previous tokens from {fid}')
				for token in tokens:
					previousTokens[token.original] = token

		if self.paths[fileid].goldFile.is_file():
			(_, wordAlignments, _) = self.alignments(fileid)
		else:
			wordAlignments = dict()

		#Workspace.log.debug(f'wordAlignments: {wordAlignments}')

		tokenizer = Tokenizer.for_extension(self.paths[fileid].ext)(
			self.resources.dictionary,
			self.resources.hmm,
			self.language,
			k,
			wordAlignments,
			previousTokens,
		)
		tokens = tokenizer.tokenize(
			self.paths[fileid].originalFile,
			force=force
		)

		if dehyphenate:
			tokens = dehyphenate_tokens(tokens)

		rows = [t.as_dict() for t in tokens]

		path = self.paths[fileid].originalTokenFile
		Workspace.log.info(f'Writing tokens to {path}')
		FileIO.save(rows, path)

		if len(wordAlignments) > 0:
			path = self.paths[fileid].goldTokenFile
			Workspace.log.info(f'Writing gold tokens to {path}')
			FileIO.save(rows, path)
		
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
			self.originalFile = CorpusFile(original.joinpath(f'{fileid}{ext}'), nheaderlines)
			self.goldFile = CorpusFile(gold.joinpath(f'{fileid}{ext}'), nheaderlines)
			self.correctedFile = CorpusFile(corrected.joinpath(f'{fileid}{ext}'), nheaderlines)
		else:
			self.originalFile = original.joinpath(f'{fileid}{ext}')
			self.goldFile = gold.joinpath(f'{fileid}{ext}')
			self.correctedFile = corrected.joinpath(f'{fileid}{ext}')
		self.originalTokenFile = training.joinpath(f'{fileid}.tokens.csv')
		self.goldTokenFile = training.joinpath(f'{fileid}.goldTokens.csv')
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
		self.hmm = HMM(config.hmmParamsFile, self.multiCharacterError)
		self.reportFile = config.reportFile
		self.heuristics = Heuristics(JSONResource(config.heuristicSettingsFile), self.dictionary)
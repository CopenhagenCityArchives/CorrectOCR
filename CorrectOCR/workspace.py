import logging
from pathlib import Path
from pprint import pformat
from typing import Dict, Iterator, List, Tuple

from . import FileAccess
from .aligner import Aligner
from .tokenize import Token, Tokenizer, tokenize_str, dehyphenate_tokens


class Workspace(object):
	log = logging.getLogger(f'{__name__}.Workspace')

	def __init__(self, workspaceconfig, resourceconfig):
		Workspace.log.info(f'Workspace configuration:\n{pformat(vars(workspaceconfig))}')
		self.nheaderlines: int = workspaceconfig.nheaderlines
		self.language = workspaceconfig.language
		self.resources = ResourceManager(resourceconfig)
		self.paths = dict()
		for file in workspaceconfig.originalPath.iterdir():
			if file.name in {'.DS_Store'}:
				continue
			fileid = file.stem
			ext = file.suffix
			self.paths[fileid] = PathManager(
				fileid,
				ext,
				workspaceconfig.originalPath,
				workspaceconfig.goldPath,
				workspaceconfig.trainingPath,
				workspaceconfig.correctedPath
			)

	def originalTokens(self) -> Iterator[Tuple[str, List[Token]]]:
		for fileid, pathManager in self.paths.items():
			if pathManager.originalTokenFile.is_file():
				Workspace.log.debug(f'Getting original tokens from {fileid}')
				yield fileid, [Token.from_dict(row) for row in FileAccess.load(pathManager.originalTokenFile, FileAccess.CSV)]

	def goldTokens(self) -> Iterator[Tuple[str, List[Token]]]:
		for fileid, pathManager in self.paths.items():
			if pathManager.goldTokenFile.is_file():
				Workspace.log.debug(f'Getting gold tokens from {fileid}')
				yield fileid, [Token.from_dict(row) for row in FileAccess.load(pathManager.goldTokenFile, FileAccess.CSV)]

	def alignments(self, fileid: str, force=False) -> Tuple[list, dict, list]:
		faPath = self.paths[fileid].fullAlignmentsFile
		waPath = self.paths[fileid].wordAlignmentsFile
		mcPath = self.paths[fileid].misreadCountsFile
		
		if not force and (faPath.is_file() and waPath.is_file() and mcPath.is_file()):
			# presume correctness, user may clean the files to rerun
			Workspace.log.info(f'Alignment files for {fileid} exist, will read and return. Use --force or clean files to rerun a subset.')
			return (
				FileAccess.load(faPath, FileAccess.JSON),
				{o: {int(k): v for k,v in i.items()} for o, i in FileAccess.load(waPath, FileAccess.JSON).items()},
				FileAccess.load(mcPath, FileAccess.JSON)
			)
		Workspace.log.info(f'Creating alignment files for {fileid}')
		
		(fullAlignments, wordAlignments, misreadCounts) = Aligner().alignments(
			tokenize_str(FileAccess.load(self.paths[fileid].originalFile), self.language.name),
			tokenize_str(FileAccess.load(self.paths[fileid].goldFile), self.language.name)
		)
		
		FileAccess.save(fullAlignments, faPath, FileAccess.JSON)
		FileAccess.save(wordAlignments, waPath, FileAccess.JSON)
		FileAccess.save(misreadCounts, mcPath, FileAccess.JSON)
		
		Workspace.log.debug(wordAlignments)
		
		return fullAlignments, wordAlignments, misreadCounts

	def tokens(self, fileid: str, k=4, dehyphenate=False, getPreviousTokens=True, force=False):
		tokenFilePath = self.paths[fileid].originalTokenFile

		if not force and tokenFilePath.is_file():
			Workspace.log.info(f'{tokenFilePath} exists and will be returned as Token objects. Use --force or delete it to rerun.')
			return [Token.from_dict(row) for row in FileAccess.load(tokenFilePath, FileAccess.CSV)]
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

		Workspace.log.debug(f'wordAlignments: {wordAlignments}')

		tokenizer = Tokenizer.for_extension(self.paths[fileid].originalFile.suffix)(
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
		FileAccess.save(rows, path, FileAccess.CSV, header=FileAccess.TOKENHEADER)

		if len(wordAlignments) > 0:
			path = self.paths[fileid].goldTokenFile
			Workspace.log.info(f'Writing gold tokens to {path}')
			FileAccess.save(rows, path, FileAccess.CSV, header=FileAccess.GOLDHEADER)
		
		return tokens


##########################################################################################


class PathManager(object):
	def __init__(self, fileid: str, ext: str, original: Path, gold: Path, training: Path, corrected: Path):
		self.originalFile = original.joinpath(f'{fileid}{ext}')
		self.goldFile = gold.joinpath(f'{fileid}{ext}')
		self.correctedFile = corrected.joinpath(f'{fileid}{ext}')
		self.originalTokenFile = training.joinpath(f'{fileid}_tokens.csv')
		self.goldTokenFile = training.joinpath(f'{fileid}_goldTokens.csv')
		self.binnedTokenFile = training.joinpath(f'{fileid}_binnedTokens.csv')
		self.fullAlignmentsFile = training.joinpath(f'{fileid}_fullAlignments.json')
		self.wordAlignmentsFile = training.joinpath(f'{fileid}_wordAlignments.json')
		self.misreadCountsFile = training.joinpath(f'{fileid}_misreadCounts.json')


##########################################################################################


class ResourceManager(object):
	log = logging.getLogger(f'{__name__}.ResourceManager')

	def __init__(self, config):
		ResourceManager.log.info(f'ResourceManager configuration:\n{pformat(vars(config))}')
		self.correctionTracking = JSONResource(config.correctionTrackingFile)
		self.memoizedCorrections = JSONResource(config.memoizedCorrectionsFile)
		self.multiCharacterError = JSONResource(config.multiCharacterErrorFile)
		from .dictionary import Dictionary
		self.dictionary = Dictionary(config.dictionaryFile, config.caseInsensitive)
		from .model import HMM
		self.hmmParamsFile = config.hmmParamsFile
		self.hmm = HMM(*FileAccess.load(self.hmmParamsFile, FileAccess.JSON), multichars=self.multiCharacterError)
		self.report = config.reportFile
		from .heuristics import Heuristics
		self.heuristics = Heuristics(JSONResource(config.heuristicSettingsFile), self.dictionary)


class JSONResource(dict):
	log = logging.getLogger(f'{__name__}.JSONResource')

	def __init__(self, path, **kwargs):
		super().__init__(**kwargs)
		JSONResource.log.info(f'Loading {path}')
		self._path = path
		data = FileAccess.load(self._path, FileAccess.JSON, default=dict())
		if data:
			self.update(data)
	
	def save(self):
		FileAccess.save(self, self._path, kind=FileAccess.JSON)

	def __repr__(self):
		return f'<JSONResource {self._path}: {dict(self)}>'

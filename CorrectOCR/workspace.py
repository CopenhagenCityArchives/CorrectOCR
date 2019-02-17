import logging
from pathlib import Path
from pprint import pformat
from typing import Iterator, Iterable, List, Tuple

from . import FileAccess
from .aligner import Aligner
from .tokenize import Token, Tokenizer, tokenize_str


class Workspace(object):
	log = logging.getLogger(f'{__name__}.Workspace')

	def __init__(self, workspaceconfig, resourceconfig):
		Workspace.log.info(f'Workspace configuration:\n{pformat(vars(workspaceconfig))}')
		self._originalPath = workspaceconfig.originalPath
		self._goldPath = workspaceconfig.goldPath
		self._trainingPath = workspaceconfig.trainingPath
		self._correctedPath = workspaceconfig.correctedPath
		self.nheaderlines: int = workspaceconfig.nheaderlines
		self.language = workspaceconfig.language
		self.resources = ResourceManager(resourceconfig)

	def originalFile(self, fileid: str) -> Path:
		for file in self._originalPath.glob(f'{fileid}.*'):
			return file # we only want the one file, not the generator
		return Path('/INVALID.ORIGINAL')

	def originalFiles(self) -> Iterable[Path]:
		return self._originalPath.iterdir()

	def goldFile(self, fileid: str) -> Path:
		for file in self._goldPath.glob(f'{fileid}.*'):
			return file # we only want the one file, not the generator
		return Path('/INVALID.GOLD')

	def goldFiles(self) -> Iterable[Path]:
		return self._goldPath.iterdir()

	def correctedFile(self, fileid: str) -> Path:
		for file in self._correctedPath.glob(f'{fileid}.*'):
			return file # we only want the one file, not the generator
		return Path('/INVALID.CORRECTED')

	def correctedFiles(self) -> Iterable[Path]:
		return self._correctedPath.iterdir()

	def fullAlignmentsFile(self, fileid: str) -> Path:
		return self._trainingPath.joinpath(f'{fileid}_fullAlignments.json')

	def wordAlignmentsFile(self, fileid: str) -> Path:
		return self._trainingPath.joinpath(f'{fileid}_wordAlignments.json')

	def misreadCountsFile(self, fileid: str) -> Path:
		return self._trainingPath.joinpath(f'{fileid}_misreadCounts.json')

	def originalTokenFile(self, fileid: str) -> Path:
		return self._trainingPath.joinpath(f'{fileid}_tokens.csv')

	def originalTokenFiles(self) -> Iterable[Path]:
		return self._trainingPath.glob(f'*_tokens.csv')

	def originalTokens(self) -> Iterator[Tuple[str, List[Token]]]:
		for file in self.originalTokenFiles():
			yield file.stem, [Token.from_dict(row) for row in FileAccess.load(file, FileAccess.CSV)]

	def goldTokenFile(self, fileid: str) -> Path:
		return self._trainingPath.joinpath(f'{fileid}_goldTokens.csv')

	def goldTokenFiles(self) -> Iterable[Path]:
		return self._trainingPath.glob(f'*_goldTokens.csv')
	
	def goldTokens(self) -> Iterator[Tuple[str, List[Token]]]:
		for goldFile in self.goldTokenFiles():
			yield goldFile.stem, [Token.from_dict(row) for row in FileAccess.load(goldFile, FileAccess.CSV)]

	def binnedTokenFile(self, fileid: str) -> Path:
		return self._trainingPath.joinpath(f'{fileid}_binnedTokens.csv')

	def alignments(self, fileid, force=False) -> Tuple[list, dict, list]:
		faPath = self.fullAlignmentsFile(fileid)
		waPath = self.wordAlignmentsFile(fileid)
		mcPath = self.misreadCountsFile(fileid)
		
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
			tokenize_str(FileAccess.load(self.originalFile(fileid)), self.language.name),
			tokenize_str(FileAccess.load(self.goldFile(fileid)), self.language.name)
		)
		
		FileAccess.save(fullAlignments, faPath, FileAccess.JSON)
		FileAccess.save(wordAlignments, waPath, FileAccess.JSON)
		FileAccess.save(misreadCounts, mcPath, FileAccess.JSON)
		
		Workspace.log.debug(wordAlignments)
		
		return fullAlignments, wordAlignments, misreadCounts

	def tokens(self, fileid, k=4, getPreviousTokens=True, force=False):
		tokenFilePath = self.originalTokenFile(fileid)
		if not force and tokenFilePath.is_file():
			Workspace.log.info(f'{tokenFilePath} exists and will be returned as Token objects. Use --force or delete it to rerun.')
			return [Token.from_dict(row) for row in FileAccess.load(tokenFilePath, FileAccess.CSV)]
		Workspace.log.info(f'Creating token files for {fileid}')
	
		# Load previously done tokens if any
		previousTokens = dict()
		if getPreviousTokens and not force:
			for fid, tokens in self.originalTokens():
				Workspace.log.debug(f'Getting previous tokens from {fid}')
				for token in tokens:
					previousTokens[token.original] = token

		if self.goldFile(fileid).is_file():
			(_, wordAlignments, _) = self.alignments(fileid)
		else:
			wordAlignments = dict()

		Workspace.log.debug(f'wordAlignments: {wordAlignments}')

		tokenizer = Tokenizer.for_extension(self.originalFile(fileid).suffix)(
			self.resources.dictionary,
			self.resources.hmm,
			self.language,
			k,
			wordAlignments,
			previousTokens,
		)
		tokens = tokenizer.tokenize(
			self.originalFile(fileid),
			force=force
		)

		rows = [t.as_dict() for t in tokens]

		path = self.originalTokenFile(fileid)
		Workspace.log.info(f'Writing tokens to {path}')
		FileAccess.save(rows, path, FileAccess.CSV, header=FileAccess.TOKENHEADER)

		if len(wordAlignments) > 0:
			path = self.goldTokenFile(fileid)
			Workspace.log.info(f'Writing gold tokens to {path}')
			FileAccess.save(rows, path, FileAccess.CSV, header=FileAccess.GOLDHEADER)
		
		return tokens


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

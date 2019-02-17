import csv
import json
import logging
from pathlib import Path
from pprint import pformat
from typing import Iterator, Iterable, Any, List, Tuple

from . import open_for_reading, ensure_new_file
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
			yield file.stem, [Token.from_dict(row) for row in Workspace.load(file, Workspace.CSV)]

	def goldTokenFile(self, fileid: str) -> Path:
		return self._trainingPath.joinpath(f'{fileid}_goldTokens.csv')

	def goldTokenFiles(self) -> Iterable[Path]:
		return self._trainingPath.glob(f'*_goldTokens.csv')
	
	def goldTokens(self) -> Iterator[Tuple[str, List[Token]]]:
		for goldFile in self.goldTokenFiles():
			yield goldFile.stem, [Token.from_dict(row) for row in Workspace.load(goldFile, Workspace.CSV)]

	def binnedTokenFile(self, fileid: str) -> Path:
		return self._trainingPath.joinpath(f'{fileid}_binnedTokens.csv')

	JSON = 'json'
	CSV = 'csv'
	DATA = 'data'

	TOKENHEADER = ['Original', '1-best', '1-best prob.', '2-best', '2-best prob.', 
				   '3-best', '3-best prob.', '4-best', '4-best prob.', 
				   'Token type', 'Token info']
	GOLDHEADER = ['Gold'] + TOKENHEADER
	BINNEDHEADER = GOLDHEADER + ['Bin', 'Heuristic', 'Decision', 'Selection']

	# TODO nheaderlines
	@classmethod
	def save(cls, data: Any, path, kind=None, header=None, backup=True):
		if not kind:
			kind = Workspace.DATA
		if backup:
			ensure_new_file(path)
		with open(path, 'w', encoding='utf-8') as f:
			if kind == Workspace.JSON:
				if not path.suffix == '.json':
					Workspace.log.error(f'Cannot save JSON to file with {path.suffix} extension! path: {path}')
					raise SystemExit(-1)
				return json.dump(data, f)
			elif kind == Workspace.CSV:
				if not path.suffix == '.csv':
					Workspace.log.error(f'Cannot save CSV to file with {path.suffix} extension! path: {path}')
					raise SystemExit(-1)
				writer = csv.DictWriter(f, header, delimiter='\t', extrasaction='ignore')
				writer.writeheader()
				return writer.writerows(data)
			else:
				return f.write(data)

	@classmethod
	def load(cls, path: Path, kind=None, default=None):
		if not kind:
			kind = Workspace.DATA
		if not path.is_file():
			return default
		with open_for_reading(path) as f:
			if kind == Workspace.JSON:
				if not path.suffix == '.json':
					Workspace.log.error(f'Cannot load JSON to file with {path.suffix} extension! path: {path}')
					raise SystemExit(-1)
				return json.load(f)
			elif kind == Workspace.CSV:
				if not path.suffix == '.csv':
					Workspace.log.error(f'Cannot load CSV to file with {path.suffix} extension! path: {path}')
					raise SystemExit(-1)
				return list(csv.DictReader(f, delimiter='\t'))
			else:
				return f.read()

	def alignments(self, fileid, force=False) -> Tuple[list, dict, list]:
		faPath = self.fullAlignmentsFile(fileid)
		waPath = self.wordAlignmentsFile(fileid)
		mcPath = self.misreadCountsFile(fileid)
		
		if not force and (faPath.is_file() and waPath.is_file() and mcPath.is_file()):
			# presume correctness, user may clean the files to rerun
			Workspace.log.info(f'Alignment files for {fileid} exist, will read and return. Use --force or clean files to rerun a subset.')
			return (
				Workspace.load(faPath, Workspace.JSON),
				{o: {int(k): v for k,v in i.items()} for o, i in Workspace.load(waPath, Workspace.JSON).items()},
				Workspace.load(mcPath, Workspace.JSON)
			)
		Workspace.log.info(f'Creating alignment files for {fileid}')
		
		(fullAlignments, wordAlignments, misreadCounts) = Aligner().alignments(
			tokenize_str(Workspace.load(self.originalFile(fileid)), self.language.name),
			tokenize_str(Workspace.load(self.goldFile(fileid)), self.language.name)
		)
		
		Workspace.save(fullAlignments, faPath, Workspace.JSON)
		Workspace.save(wordAlignments, waPath, Workspace.JSON)
		Workspace.save(misreadCounts, mcPath, Workspace.JSON)
		
		Workspace.log.debug(wordAlignments)
		
		return fullAlignments, wordAlignments, misreadCounts

	def tokens(self, fileid, k=4, getPreviousTokens=True, force=False):
		tokenFilePath = self.originalTokenFile(fileid)
		if not force and tokenFilePath.is_file():
			Workspace.log.info(f'{tokenFilePath} exists and will be returned as Token objects. Use --force or delete it to rerun.')
			return [Token.from_dict(row) for row in Workspace.load(tokenFilePath, Workspace.CSV)]
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
		Workspace.save(rows, path, Workspace.CSV, header=Workspace.TOKENHEADER)
	
		if len(wordAlignments) > 0:
			path = self.goldTokenFile(fileid)
			Workspace.log.info(f'Writing gold tokens to {path}')
			Workspace.save(rows, path, Workspace.CSV, header=Workspace.GOLDHEADER)
		
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
		self.hmm = HMM(*Workspace.load(self.hmmParamsFile, Workspace.JSON), multichars=self.multiCharacterError)
		self.report = config.reportFile
		from .heuristics import Heuristics
		self.heuristics = Heuristics(JSONResource(config.heuristicSettingsFile), self.dictionary)


class JSONResource(dict):
	log = logging.getLogger(f'{__name__}.JSONResource')

	def __init__(self, path, **kwargs):
		super().__init__(**kwargs)
		JSONResource.log.info(f'Loading {path}')
		self._path = path
		data = Workspace.load(self._path, Workspace.JSON, default=dict())
		if data:
			self.update(data)
	
	def save(self):
		Workspace.save(self, self._path, kind=Workspace.JSON)

	def __repr__(self):
		return f'<JSONResource {self._path}: {dict(self)}>'

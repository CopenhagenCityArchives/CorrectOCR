import collections
import csv
import json
import logging
from pprint import pformat

import requests

from . import open_for_reading, ensure_new_file
from .dictionary import Dictionary
from .aligner import Aligner
from .model import HMM
from .tokenize.string import StringToken, StringTokenizer, tokenize_string
from .heuristics import Heuristics


class Workspace(object):
	def __init__(self, workspaceconfig, resourceconfig):
		self.log = logging.getLogger(f'{__name__}.Workspace')
		self.log.info(f'Workspace configuration:\n{pformat(vars(workspaceconfig))}')
		self._originalPath = workspaceconfig.originalPath
		self._goldPath = workspaceconfig.goldPath
		self._trainingPath = workspaceconfig.trainingPath
		self._correctedPath = workspaceconfig.correctedPath
		self.resources = ResourceManager(resourceconfig)

	def originalFile(self, fileid):
		return self._originalPath.joinpath(f'{fileid}.txt')

	def originalFiles(self):
		return self._originalPath.iterdir()

	def goldFile(self, fileid):
		return self._goldPath.joinpath(f'{fileid}.txt')

	def goldFiles(self):
		return self._goldPath.iterdir()

	def correctedFile(self, fileid):
		return self._correctedPath.joinpath(f'{fileid}.txt')

	def correctedFiles(self):
		return self._correctedPath.iterdir()

	def fullAlignmentsFile(self, fileid):
		return self._trainingPath.joinpath(f'{fileid}_fullAlignments.json')

	def wordAlignmentsFile(self, fileid):
		return self._trainingPath.joinpath(f'{fileid}_wordAlignments.json')

	def misreadCountsFile(self, fileid):
		return self._trainingPath.joinpath(f'{fileid}_misreadCounts.json')

	def tokenFile(self, fileid):
		return self._trainingPath.joinpath(f'{fileid}_tokens.csv')

	def tokenFiles(self):
		return self._trainingPath.glob(f'*_tokens.csv')

	def goldTokenFile(self, fileid):
		return self._trainingPath.joinpath(f'{fileid}_goldTokens.csv')

	def binnedTokenFile(self, fileid):
		return self._trainingPath.joinpath(f'{fileid}_binnedTokens.csv')
	
	JSON = 'json'
	CSV = 'csv'
	DATA = 'data'

	TOKENHEADER = ['Original', '1-best', '1-best prob.', '2-best', '2-best prob.', '3-best', '3-best prob.', '4-best', '4-best prob.']
	GOLDHEADER = ['Gold'] + TOKENHEADER
	BINNEDHEADER = GOLDHEADER + ['bin', 'heuristic', 'decision', 'selection']
	
	#TODO nheaderlines
	def save(data, path, kind=None, header=None, backup=True):
		if not kind:
			kind = Workspace.DATA
		if backup:
			path = ensure_new_file(path)
		with open(path, 'w', encoding='utf-8') as f:
			if kind == Workspace.JSON:
				if not path.suffix == '.json':
					logging.getLogger(f'{__name__}.Workspace').error(f'Cannot save JSON to file with {path.suffix} extension! path: {path}')
					raise SystemExit(-1)
				return json.dump(data, f)
			elif kind == Workspace.CSV:
				if not path.suffix == '.csv':
					logging.getLogger(f'{__name__}.Workspace').error(f'Cannot save CSV to file with {path.suffix} extension! path: {path}')
					raise SystemExit(-1)
				writer = csv.DictWriter(f, header, delimiter='\t', extrasaction='ignore')
				writer.writeheader()
				return writer.writerows(data)
			else:
				return f.write(data)
	
	def load(path, kind=None, default=None):
		if not kind:
			kind = Workspace.DATA
		if not path.is_file():
			return default
		with open_for_reading(path) as f:
			if kind == Workspace.JSON:
				if not path.suffix == '.json':
					self.log.error(f'Cannot load JSON to file with {path.suffix} extension! path: {path}')
					raise SystemExit(-1)
				return json.load(f)
			elif kind == Workspace.CSV:
				if not path.suffix == '.csv':
					self.log.error(f'Cannot load CSV to file with {path.suffix} extension! path: {path}')
					raise SystemExit(-1)
				return list(csv.DictReader(f, delimiter='\t'))
			else:
				return f.read()
	

	def alignments(self, fileid, language='English', force=False):
		faPath = self.fullAlignmentsFile(fileid)
		waPath = self.wordAlignmentsFile(fileid)
		mcPath = self.misreadCountsFile(fileid)
		
		if not force and (faPath.is_file() and waPath.is_file() and mcPath.is_file()):
			# presume correctness, user may clean the files to rerun
			self.log.info(f'Alignment files for {fileid} exist, will read and return. Use --force or clean files to rerun a subset.')
			return (
				Workspace.load(faPath, Workspace.JSON),
				{o: {int(k): v for k,v in i.items()} for o, i in Workspace.load(waPath, Workspace.JSON).items()},
				Workspace.load(mcPath, Workspace.JSON)
			)
		self.log.info(f'Creating alignment files for {fileid}')
		
		(fullAlignments, wordAlignments, misreadCounts) = Aligner().alignments(
			tokenize_string(Workspace.load(self.originalFile(fileid)), language),
			tokenize_string(Workspace.load(self.goldFile(fileid)), language),
			force=force
		)
		
		Workspace.save(fullAlignments, faPath, Workspace.JSON)
		Workspace.save(wordAlignments, waPath, Workspace.JSON)
		Workspace.save(misreadCounts, mcPath, Workspace.JSON)
		
		self.log.debug(wordAlignments)
		
		return (fullAlignments, wordAlignments, misreadCounts)		


	def tokens(self, fileid, nheaderlines=0, k=4, language='English', getWordAlignments=True, force=False):
		tokenFilePath = self.tokenFile(fileid)
		if not force and tokenFilePath.is_file():
			self.log.info(f'{tokenFilePath} exists and will be returned as StringToken objects. Use --force or delete it to rerun.')
			return [StringToken.from_dict(t) for t in Workspace.load(tokenFilePath, Workspace.CSV)]
		self.log.info(f'Creating token files for {fileid}')
	
		# Load previously done tokens if any
		previousTokens = dict()
		for file in self.tokenFiles():
			for row in Workspace.load(file, Workspace.CSV):
				previousTokens[row['Original']] = StringToken.from_dict(row)

		if getWordAlignments:
			(_, wordAlignments, _) = self.alignments(fileid)
		else:
			wordAlignments = dict()

		self.log.debug(f'wordAlignments: {wordAlignments}')

		tokenizer = StringTokenizer(
			self.resources.dictionary,
			self.resources.hmm,
			language,
			wordAlignments,
			previousTokens,
		)
		tokens = tokenizer.tokenize(
			self.originalFile(fileid),
			nheaderlines=nheaderlines,
			k=k,
			force=force
		)

		rows = [t.as_dict() for t in tokens]

		path = self.tokenFile(fileid)
		self.log.info(f'Writing tokens to {path}')
		Workspace.save(rows, path, Workspace.CSV, header=Workspace.TOKENHEADER)
	
		if len(wordAlignments) > 0:
			path = self.goldTokenFile(fileid)
			self.log.info(f'Writing gold tokens to {path}')
			Workspace.save(rows, path, Workspace.CSV, header=Workspace.GOLDHEADER)
		
		return tokens


##########################################################################################


class ResourceManager(object):
	def __init__(self, config):
		self.log = logging.getLogger(f'{__name__}.ResourceManager')
		self.log.info(f'ResourceManager configuration:\n{pformat(vars(config))}')
		self.correctionTracking = JSONResource(config.correctionTrackingFile)
		self.memoizedCorrections = JSONResource(config.memoizedCorrectionsFile)
		self.multiCharacterError = JSONResource(config.multiCharacterErrorFile)
		self.dictionary = Dictionary(config.dictionaryFile, config.caseInsensitive)
		self.hmmParamsFile = config.hmmParamsFile
		self.hmm = HMM(*Workspace.load(self.hmmParamsFile, Workspace.JSON), multichars=self.multiCharacterError)
		self.report = config.reportFile
		self.heuristics = Heuristics(JSONResource(config.heuristicSettingsFile), self.dictionary)


class JSONResource(dict):
	def __init__(self, path):
		self.log = logging.getLogger(f'{__name__}.JSONResource')
		self.log.info(f'Loading {path}')
		self._path = path
		data = Workspace.load(self._path, Workspace.JSON, default=dict())
		if data:
			self.update(data)
	
	def save(self):
		Workspace.save(self, self._path, kind=Workspace.JSON)

	def __repr__(self):
		return f'<JSONResource {self._path}: {dict(self)}>'

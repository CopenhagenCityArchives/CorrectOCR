from __future__ import annotations

import logging
import re
import urllib
from pathlib import Path, PurePath
from pprint import pformat
from typing import Any, Dict, Iterator, List, Tuple

import requests

from ._cache import LRUCache, cached
from .dictionary import Dictionary
from .document import Document
from .fileio import FileIO
from .heuristics import Heuristics
from .model.hmm import HMM


class Workspace(object):
	"""
	The Workspace holds references to :class:`Documents<CorrectOCR.workspace.Document>` and resources used by the various :mod:`commands<CorrectOCR.commands>`.

	:param workspaceconfig: An object with the following properties:

	   -  **nheaderlines** (:class:`int`): The number of header lines in corpus texts.
	   -  **language**: A language instance from `pycountry <https://pypi.org/project/pycountry/>`.
	   -  **originalPath** (:class:`Path<pathlib.Path>`): Directory containing the original docs.
	   -  **goldPath** (:class:`Path<pathlib.Path>`): Directory containing the gold (if any) docs.
	   -  **trainingPath** (:class:`Path<pathlib.Path>`): Directory for storing intermediate docs.
	   -  **docInfoBaseURL** (:class:`str`): Base URL that when appended with a doc_id provides information about documents.

	:param resourceconfig: Passed directly to :class:`ResourceManager<CorrectOCR.workspace.ResourceManager>`, see this for further info.
	
	:param storageconfig: TODO
	"""
	log = logging.getLogger(f'{__name__}.Workspace')

	def __init__(self, workspaceconfig, resourceconfig, storageconfig):
		self.config = workspaceconfig
		self.storageconfig = storageconfig
		self.root = self.config.rootPath.resolve()
		FileIO.cacheRoot = self.root.joinpath('__COCRCache__')
		self.storageconfig.trainingPath = self.root.joinpath(self.config.trainingPath) # hacky...
		self._originalPath = self.root.joinpath(self.config.originalPath)
		Workspace.log.info(f'Workspace configuration:\n{pformat(vars(self.config))} at {self.root}')
		Workspace.log.info(f'Storage configuration:\n{pformat(vars(self.storageconfig))}')
		self.nheaderlines: int = self.config.nheaderlines
		self.docInfoBaseURL: int = self.config.docInfoBaseURL
		self.resources = ResourceManager(self.root, resourceconfig)
		self.docs: Dict[str, Document] = dict()
		Workspace.log.info(f'Adding documents from: {self._originalPath}')
		for file in self._originalPath.iterdir():
			if file.name in {'.DS_Store'}:
				continue
			self.add_doc(file)
		Workspace.log.info(f'Workspace documents: {self.docs}')
		self.cache = LRUCache(maxsize=1000)

	def add_doc(self, doc: Any) -> str:
		"""
		Initializes a new :class:`Document<CorrectOCR.workspace.Document>` and adds it to the
		workspace.

		The doc_id of the document will be determined by its filename.

		If the file is not in the originalPath, it will be copied or downloaded there.

		:param doc: A path or URL.
		"""
		self.log.debug(f'Preparing to add {doc}')
		if isinstance(doc, PurePath):
			if doc.parent != self._originalPath:
				FileIO.copy(doc, self._originalPath)
		elif isinstance(doc, str) and doc[:4] == 'http':
			url = urllib.parse.urlparse(doc)
			new_doc_file = self._originalPath.joinpath(Path(url.path).name)
			r = requests.get(url.geturl())
			if r.status_code == 200:
				new_doc_file = new_doc_file.with_suffix('.pdf') # TODO mimetype => suffix
				with open(new_doc_file, 'wb') as f:
					f.write(r.content)
			else:
				self.log.error(f'Unable to save file: {r}')
			doc = new_doc_file
		else:
			raise ValueError(f'Cannot add doc from reference of unknown type: {type(doc)} {doc}')

		document = Document(
			self,
			doc,
			self.root.joinpath(self.config.originalPath).resolve(),
			self.root.joinpath(self.config.goldPath).resolve(),
			self.root.joinpath(self.config.trainingPath).resolve(),
			self.nheaderlines,
		)
		self.docs[document.docid] = document
		Workspace.log.debug(f'Added {document.docid}: {document}')
		
		return document.docid

	def docids_for_ext(self, ext: str, server_ready=False, is_done=False) -> List[str]:
		"""
		Returns a list of IDs for documents with the given extension.
		
		:param: ext Only include docs with this extension.
		:param: server_ready Only include documents that are ready (prepared).
		"""
		for docid, doc in self.docs.items():
			if doc.ext != ext:
				continue
			if server_ready and not doc.tokens.server_ready:
				continue
			if is_done and not doc.is_done:
				continue
			yield docid

	def original_tokens(self) -> Iterator[Tuple[str, 'TokenList']]:
		"""
		Yields an iterator of (docid, list of tokens).
		"""
		for docid, doc in self.docs.items():
			Workspace.log.debug(f'Getting original tokens from {docid}')
			yield docid, doc.tokens

	def gold_tokens(self) -> Iterator[Tuple[str, 'TokenList']]:
		"""
		Yields an iterator of (docid, list of gold-aligned tokens).
		"""
		for docid, doc in self.docs.items():
			if doc.is_done:
				doc.prepare('align', doc.tokens[0].k) # hacky way to get k...
				Workspace.log.debug(f'Getting gold tokens from {docid}')
				yield docid, [t for t in doc.tokens if t.gold is not None]

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
		self.dictionary = Dictionary(self.root.joinpath(config.dictionaryPath).resolve(), config.ignoreCase)
		self.hmm = HMM(self.root.joinpath(config.hmmParamsFile).resolve(), self.multiCharacterError)
		self.reportFile = self.root.joinpath(config.reportFile).resolve()
		self.heuristics = Heuristics(JSONResource(self.root.joinpath(config.heuristicSettingsFile).resolve()), self.dictionary)

from __future__ import annotations

import itertools
import logging
import re
import requests
import urllib
from pathlib import Path, PurePath
from pprint import pformat
from typing import Any, Dict, Iterator, List, Tuple, Union

import progressbar

from ._cache import LRUCache, cached
from .aligner import Aligner
from .dictionary import Dictionary
from .fileio import FileIO
from .heuristics import Heuristics
from .model import HMM
from .tokens import Tokenizer, TokenList, tokenize_str


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

	def docids_for_ext(self, ext: str, server_ready=False) -> List[str]:
		"""
		Returns a list of IDs for documents with the given extension.
		
		:param: ext Only include docs with this extension.
		:param: server_ready Only include documents that are ready (prepared).
		"""
		return [docid for docid, doc in self.docs.items() if doc.ext == ext and not (server_ready and not doc.tokens.server_ready)]

	def original_tokens(self) -> Iterator[Tuple[str, TokenList]]:
		"""
		Yields an iterator of (docid, list of tokens).
		"""
		for docid, doc in self.docs.items():
			Workspace.log.debug(f'Getting original tokens from {docid}')
			yield docid, doc.tokens

	def gold_tokens(self) -> Iterator[Tuple[str, TokenList]]:
		"""
		Yields an iterator of (docid, list of gold-aligned tokens).
		"""
		for docid, doc in self.docs.items():
			if doc.goldFile.is_file():
				doc.prepare('align', self.config.k)
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


def window(iterable, size=3):
    """Generate a sliding window of values."""
    its = itertools.tee(iterable, size)
    return zip(*(itertools.islice(it, index, None) for index, it in enumerate(its)))


class Document(object):
	log = logging.getLogger(f'{__name__}.Document')

	"""
	Documents provide access to paths and :class:`Tokens<CorrectOCR.tokens.Token>`.
	"""
	def __init__(self, workspace: Workspace, doc: Path, original: Path, gold: Path, training: Path, nheaderlines: int = 0):
		"""
		:param doc: A path to a file.
		:param original: Directory for original uncorrected files.
		:param gold: Directory for known correct "gold" files (if any).
		:param training: Directory for storing intermediate files.
		:param nheaderlines: Number of lines in file header (only relevant for ``.txt`` files)
		"""
		self.workspace = workspace
		self.docid = doc.stem
		self.ext = doc.suffix
		if self.docid is None:
			raise ValueError(f'Cannot get docid from {doc}')
		self.info_url = None #: URL that provides information about the document
		if self.workspace.docInfoBaseURL:
			self.info_url = self.workspace.docInfoBaseURL + self.docid
		Document.log.info(f'Document {self.docid} has info_url: {self.info_url}')
		if self.ext == '.txt':
			self.originalFile: Union[CorpusFile, Path] = CorpusFile(original.joinpath(doc.name), nheaderlines)
			self.goldFile: Union[CorpusFile, Path] = CorpusFile(gold.joinpath(doc.name), nheaderlines)
		else:
			self.originalFile: Union[CorpusFile, Path] = original.joinpath(doc.name)
			self.goldFile: Union[CorpusFile, Path] = gold.joinpath(doc.name)
		if not self.originalFile.exists():
			raise ValueError(f'Cannot create Document with non-existing original file: {self.originalFile}')
		self.tokenFile = training.joinpath(f'{self.docid}.csv')  #: Path to token file (CSV format).
		self.fullAlignmentsFile = training.joinpath(f'{self.docid}.fullAlignments.json')  #: Path to full letter-by-letter alignments (JSON format).
		self.wordAlignmentsFile = training.joinpath(f'{self.docid}.wordAlignments.json')  #: Path to word-by-word alignments (JSON format).
		self.readCountsFile = training.joinpath(f'{self.docid}.readCounts.json')  #: Path to letter read counts (JSON format).
		
		self.tokens = TokenList.new(self.workspace.storageconfig)
		if TokenList.exists(self.workspace.storageconfig, self.docid):
			self.tokens.load(self.docid)
			Document.log.debug(f'Loaded {len(self.tokens)} tokens.')

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

		#Document.log.debug(f'wordAlignments: {wordAlignments}')
		
		return fullAlignments, wordAlignments, readCounts

	def prepare(self, step: str, k: int, dehyphenate=False, force=False):
		"""
		Prepares the :class:`Tokens<CorrectOCR.tokens.Token>` for the given doc.

		Possible steps are:

		   -  ``tokenize``: basic tokenizaton
		   -  ``align``: alignment of original and gold tokens
		   -  ``kbest`` calculates *k*-best correction candidates for each
		      token via the HMM
		   -  ``bin``: sorts the tokens into *bins* according to the
		      :py:mod:`Heuristics<CorrectOCR.heuristics>`
		   -  ``autocorrect`` generates corrections where possible,
		      ie. tokens not marked for manual annotation
		   -  ``server``: performs all steps necessary for the backend server to work
		   -  ``all``: performs all steps, including possible future ones

		*Note*: To force retokenization from the ground up, the ``step`` parameter
		must be explicitly set to ``tokenize`` (and of course the ``force`` parameter
		must be set to ``True``).

		:param step: Which step to perform.
		:param k: How many `k`-best suggestions to calculate, if necessary.
		:param dehyphenate: Whether to attempt dehyphenization of tokens.
		:param force: Back up existing tokens and create new ones.
		"""
		log = logging.getLogger(f'{__name__}._get_prep_step')

		prep_methods = {
			'server': 'autocorrect',
			'all': 'autocorrect',
		}
		step = prep_methods.get(step, step)
		Document.log.info(f'Creating {step} tokens for {self.docid}')

		if step == 'tokenize':
			if force or len(self.tokens) == 0:
				tokenizer = Tokenizer.for_extension(self.ext)(self.workspace.config.language)
				self.tokens = tokenizer.tokenize(
					self.originalFile,
					self.workspace.storageconfig
				)
				if dehyphenate:
					self.tokens.dehyphenate()
		elif step == 'align':
			self.prepare('tokenize', k, dehyphenate)
			if self.goldFile.is_file():
				(_, wordAlignments, _) = self.alignments()
				for i, token in enumerate(self.tokens): # TODO force
					if not token.gold and token.original in wordAlignments:
						wa = wordAlignments[token].items()
						closest = sorted(wa, key=lambda x: abs(x[0]-i))
						#Document.log.debug(f'{wa} {i} {token.original} {closest}')
						token.gold = closest[0][1]
		elif step == 'kbest':
			if self.goldFile.is_file():
				self.prepare('align', k, dehyphenate, force)
			else:
				self.prepare('tokenize', k, dehyphenate)
			self.workspace.resources.hmm.generate_kbest(self.tokens, k, force)
		elif step == 'bin':
			self.prepare('kbest', k, dehyphenate, force)
			self.workspace.resources.heuristics.bin_tokens(self.tokens, force)
		elif step == 'autocorrect':
			self.prepare('bin', k, dehyphenate, force)
			for t in progressbar.progressbar(self.tokens):
				if force or not t.gold:
					if t.decision in {'kbest', 'kdict'}:
						t.gold = t.kbest[int(t.selection)].candidate
					elif t.decision == 'original':
						t.gold = t.original
			Document.log.info(f'Marking {self.docid} ready for server')
		
		self.tokens.save()

	def crop_tokens(self, edge_left = None, edge_right = None):
		Document.log.info(f'Cropping tokens for {self.docid}')
		Tokenizer.for_extension(self.ext).crop_tokens(self.originalFile, self.workspace.storageconfig, self.tokens)
		self.tokens.save()

	def precache_images(self, complete=False):
		Document.log.info(f'Precaching images for {self.docid}')
		if complete:
			for token in progressbar.progressbar(self.tokens):
				_, _ = token.extract_image(self.workspace)
		else:
			for l, token, r in progressbar.progressbar(list(window(self.tokens))):
				if token.decision == 'annotator' and not token.is_discarded:
					_, _ = l.extract_image(self.workspace)
					_, _ = token.extract_image(self.workspace)
					_, _ = r.extract_image(self.workspace)


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

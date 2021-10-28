from __future__ import annotations

import datetime
import itertools
import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Union

import progressbar

from .aligner import Aligner
from .fileio import FileIO
from .tokens import Tokenizer, TokenList, tokenize_str


def window(iterable, size=3):
    """Generate a sliding window of values."""
    its = itertools.tee(iterable, size)
    return zip(*(itertools.islice(it, index, None) for index, it in enumerate(its)))


@dataclass
class Document(object):
	log = logging.getLogger(f'{__name__}.Document')
	
	workspace: Workspace
	path: str
	doc_id: str = None #: The 
	mimetype: str = None #: The mimetype of the document
	date_added: datetime.datetime = None #: When the document was added to the system
	info_url: str = None #: A URL pointing to further information about the document, if necessary
	nheaderlines: int = None #: Number of lines in file header (only relevant for ``.txt`` / ``text/plain`` files)

	"""
	Documents provide access to paths and :class:`Tokens<CorrectOCR.tokens.Token>`.
	"""
	def __post_init__(self):
		self._server_ready = False
		self._is_done = False
		self.workspace = workspace
		self.doc_id = doc.stem
		self.mimetype = mimetypes.guess_type(doc)
		if self.doc_id is None:
			raise ValueError(f'Cannot get doc_id from {doc}')
		self.info_url = None #: URL that provides information about the document
		if self.workspace.docInfoBaseURL:
			self.info_url = self.workspace.docInfoBaseURL + self.doc_id
			Document.log.info(f'Document {self.doc_id} has info_url: {self.info_url}')
		if self.mimetype == 'text/plain':
			self.originalFile: Union[CorpusFile, Path] = CorpusFile(self.path, nheaderlines)
			self.goldFile: Union[CorpusFile, Path] = CorpusFile(self.path, nheaderlines)
		else:
			self.originalFile: Union[CorpusFile, Path] = self.path
			self.goldFile: Union[CorpusFile, Path] = self.path
		if not self.originalFile.exists():
			raise ValueError(f'Cannot create Document with non-existing original file: {self.originalFile}')
		
		self.tokens = TokenList.new(self.workspace.storageconfig, doc_id=self.doc_id)
		self.tokens.load()
		Document.log.debug(f'Loaded {len(self.tokens)} tokens. Stats: {self.tokens.stats}')

	@classmethod
	def get_id(cls, doc):
		return doc.stem

	@property
	def is_done(self):
		if not self._is_done:
			self._is_done = self.tokens.stats['done']
		return self._is_done
		
	@property
	def server_ready(self):
		if not self._server_ready:
			self._server_ready = self.tokens.server_ready
		return self._server_ready

	@property
	def alignments(self):
		if not self.is_done:
			Document.log.error(f'Cannot create alignments for non-done document {self.docid}!')
			return None
		return Aligner().alignments(self.tokens, FileIO.cachePath('alignments').joinpath(f'{self.docid}.json'))

	def prepare(self, step: str, k: int, dehyphenate=False, force=False):
		"""
		Prepares the :class:`Tokens<CorrectOCR.tokens.Token>` for the given doc.

		Possible steps are:

		   -  ``tokenize``: basic tokenizaton
		   -  ``autocrop``: crop tokens near edges
		   -  ``rehyphenate``: redoes hyphenation
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
		Document.log.info(f'Running step "{step}" for {self.docid} (k = {k}, dehyphenate = {dehyphenate}, force = {force})')

		tokens_modified = False

		if step == 'tokenize':
			if force or len(self.tokens) == 0:
				tokenizer = Tokenizer.for_type(self.mimetype)(self.workspace.config.language)
				self.tokens = tokenizer.tokenize(
					self.originalFile,
					self.workspace.storageconfig
				)
				if dehyphenate:
					Document.log.info(f'Document {self.doc_id} will be dehyphenated')
					self.tokens.dehyphenate()
				tokens_modified = True
			else:
				Document.log.info(f'Document {self.doc_id} is already tokenized. Use --force to recreate tokens (this will destroy suggestions and corrections).')
				return
		elif step == 'autocrop':
			self.prepare('tokenize', k, dehyphenate)
			self.tokens.crop_tokens()
			tokens_modified = True
		elif step == 'rehyphenate':
			self.tokens.dehyphenate()
			tokens_modified = True
		elif step == 'kbest':
			self.prepare('tokenize', k, dehyphenate)
			tokens_modified = self.workspace.resources.hmm.generate_kbest(self.tokens, k, force)
		elif step == 'bin':
			self.prepare('kbest', k, dehyphenate, force)
			tokens_modified = self.workspace.resources.heuristics.bin_tokens(self.tokens, force)
		elif step == 'autocorrect':
			self.prepare('bin', k, dehyphenate, force)
			for t in progressbar.progressbar(self.tokens):
				if force or not t.gold:
					if t.heuristic in {'kbest', 'kdict'}:
						t.gold = t.kbest[int(t.selection)].candidate
					elif t.heuristic == 'original':
						t.gold = t.original
					tokens_modified = True
		
		if tokens_modified:
			self.tokens.save()

	def crop_tokens(self, edge_left = None, edge_right = None):
		Document.log.info(f'Cropping tokens for {self.doc_id}')
		Tokenizer.for_type(self.mimetype).crop_tokens(self.originalFile, self.workspace.storageconfig, self.tokens, edge_left, edge_right)
		self.tokens.save()

	def precache_images(self, complete=False):
		Document.log.info(f'Precaching images for {self.doc_id}')
		if complete:
			Document.log.info(f'Generating ALL images.')
			for token in progressbar.progressbar(self.tokens):
				_, _ = token.extract_image(self.workspace)
		else:
			Document.log.info(f'Generating images for annotation.')
			count = 0
			for l, token, r in progressbar.progressbar(list(window(self.tokens))):
				if ('annotator' in (l.heuristic, token.heuristic, r.heuristic) or l.is_hyphenated) and not token.is_discarded:
					_, _ = l.extract_image(self.workspace)
					_, _ = token.extract_image(self.workspace)
					_, _ = r.extract_image(self.workspace)
					count += 1
			Document.log.info(f'Generated images for {count} tokens.')

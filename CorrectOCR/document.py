from __future__ import annotations

import itertools
import logging
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


class Document(object):
	log = logging.getLogger(f'{__name__}.Document')

	"""
	Documents provide access to paths and :class:`Tokens<CorrectOCR.tokens.Token>`.
	"""
	def __init__(self, workspace: Workspace, docid: str, ext: str, original: Path, gold: Path, nheaderlines: int = 0):
		"""
		:param doc: A filename stem.
		:param ext: An extension (eg. '.pdf')
		:param original: Directory for original uncorrected files.
		:param gold: Directory for known correct "gold" files (if any).
		:param nheaderlines: Number of lines in file header (only relevant for ``.txt`` files)
		"""
		self._server_ready = False
		self._is_done = False
		self._tokens = None
		self.workspace = workspace
		self.docid = docid
		self.ext = ext
		self.info_url = None #: URL that provides information about the document
		with self.workspace.storageconfig.connection.cursor(named_tuple=True, buffered=True) as cursor:
			cursor.execute("""
				SELECT
					doc_id,
					ext,
					original_path,
					gold_path,
					is_done
				FROM documents
				WHERE 
					doc_id = %s AND
					ext = %s
				""", (
					self.docid,
					self.ext,
				)
			)
			result = cursor.fetchone()
			Document.log.info(result)
			if result is not None:
				if self.docid != result.doc_id or self.ext != result.ext:
					raise ValueError('Mismatching doc_id or extension!')
				self.original_path = Path(result.original_path)
				self.gold_path = Path(result.gold_path)
				self._is_done = result.is_done
			else:
				if self.workspace.docInfoBaseURL:
					self.info_url = self.workspace.docInfoBaseURL + self.docid
				Document.log.info(f'Document {self.docid} has info_url: {self.info_url}')
				name = self.docid + self.ext
				if self.ext == '.txt':
					self.original_path: Union[CorpusFile, Path] = CorpusFile(original.joinpath(name), nheaderlines)
					self.gold_path: Union[CorpusFile, Path] = CorpusFile(gold.joinpath(name), nheaderlines)
				else:
					self.original_path: Union[CorpusFile, Path] = original.joinpath(name)
					self.gold_path: Union[CorpusFile, Path] = gold.joinpath(name)
				cursor.execute("""
						INSERT INTO documents (
							doc_id,
							ext,
							original_path,
							gold_path,
							is_done
						) VALUES (
							%s, %s, %s, %s, %s
						)
					""", (
						self.docid,
						self.ext,
						str(self.original_path),
						str(self.gold_path),
						self._is_done,
					)
				)
				self.workspace.storageconfig.connection.commit()

	@property
	def tokens(self):
		if self._tokens is None:
			self._tokens = TokenList.new(self.workspace.storageconfig, docid=self.docid)
			self._tokens.load()
			Document.log.debug(f'Loaded {len(self._tokens)} tokens. Stats: {self._tokens.stats}')
		return self._tokens

	@classmethod
	def get_all(cls, workspace):
		docs = dict()
		with workspace.storageconfig.connection.cursor(named_tuple=True, buffered=True) as cursor:
			cursor.execute("""
				SELECT
					doc_id,
					ext,
					original_path,
					gold_path,
					is_done
				FROM documents
				ORDER BY doc_id
				"""
			)
			for result in cursor.fetchall():
				doc = Document(
					workspace,
					result.doc_id,
					result.ext,
					Path(result.original_path),
					Path(result.gold_path)
				)
				doc._is_done = result.is_done
				docs[result.doc_id] = doc
		return docs

	@property
	def is_done(self):
		if not self._is_done:
			self._is_done = self.tokens.stats['done']
			if self._is_done:
				with self.workspace.storageconfig.connection.cursor(named_tuple=True, buffered=True) as cursor:
					cursor.execute("""
						UPDATE documents
						SET is_done = TRUE
						WHERE 
							doc_id = %s AND
							ext = %s
						""", (
							self.docid,
							self.ext,
						)
					)
					self.workspace.storageconfig.connection.commit()
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
				tokenizer = Tokenizer.for_type(self.ext)(self.workspace.config.language)
				self._tokens = tokenizer.tokenize(
					self.original_path,
					self.workspace.storageconfig
				)
				if dehyphenate:
					Document.log.info(f'Document {self.docid} will be dehyphenated')
					self.tokens.dehyphenate()
				tokens_modified = True
			else:
				Document.log.info(f'Document {self.docid} is already tokenized. Use --force to recreate tokens (this will destroy suggestions and corrections).')
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
		Document.log.info(f'Cropping tokens for {self.docid}')
		Tokenizer.for_type(self.ext).crop_tokens(self.original_path, self.workspace.storageconfig, self.tokens, edge_left, edge_right)
		self.tokens.save()

	def precache_images(self, complete=False):
		Document.log.info(f'Precaching images for {self.docid}')
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
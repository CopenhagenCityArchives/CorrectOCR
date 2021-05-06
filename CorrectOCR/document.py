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
		
		self.tokens = TokenList.new(self.workspace.storageconfig, docid=self.docid)
		self.tokens.load()
		Document.log.debug(f'Loaded {len(self.tokens)} tokens. Stats: {self.tokens.stats}')

	@property
	def is_done(self):
		return self.tokens.stats['done']

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
		   -  ``rehyphenate``: redoes hyphenation
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
			else:
				Document.log.info(f'Document {self.docid} is already tokenized. Use --force to recreate tokens (this will destroy suggestions and corrections).')
				return
		elif step == 'rehyphenate':
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
		
		self.tokens.save()

	def crop_tokens(self, edge_left = None, edge_right = None):
		Document.log.info(f'Cropping tokens for {self.docid}')
		Tokenizer.for_extension(self.ext).crop_tokens(self.originalFile, self.workspace.storageconfig, self.tokens, edge_left, edge_right)
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
				if (token.decision == 'annotator' or l.is_hyphenated) and not token.is_discarded:
					_, _ = l.extract_image(self.workspace)
					_, _ = token.extract_image(self.workspace)
					_, _ = r.extract_image(self.workspace)
					count += 1
			Document.log.info(f'Generated images for {count} tokens.')
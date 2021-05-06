import collections
import logging
from typing import Counter, DefaultDict, Dict, List, Optional, Tuple

from ._util import punctuationRE
from .tokens.list import TokenList

import progressbar

class Aligner(object):
	log = logging.getLogger(f'{__name__}.Aligner')

	def __init__(self):
		self._fullAlignments: Optional[List[List[str, str]]] = None
		self._wordAlignments: Optional[DefaultDict[str, Dict[int, str]]] = None
		self._readCounts: Optional[DefaultDict[str, Counter[str]]] = None

	def alignments(self, tokens: TokenList):
		"""
		Aligns the original and gold tokens in order to discover the corrections that have been made.

		:param tokens: A TokenList
		:return: A tuple with three elements:

		   -  ``fullAlignments`` -- A list of letter-by-letter alignments (2-element tuples)
		   -  ``wordAlignments``--
		   -  ``readCounts`` -- A dictionary of counts of aligned reads for each character.
		"""
		self._fullAlignments: List[Tuple[str, str]] = []
		self._wordAlignments: DefaultDict[str, Dict[int, str]] = collections.defaultdict(dict)
		self._readCounts: DefaultDict[str, Counter[str]] = collections.defaultdict(collections.Counter)
		
		Aligner.log.info(f'Aligning {len(tokens)} tokens')
		for token in progressbar.progressbar(tokens):
			self._wordAlignments[token.original][token.index] = token.gold
			for leftChar, rightChar in zip(token.original, token.gold):
				self._fullAlignments.append((leftChar, rightChar))
				self._readCounts[leftChar][rightChar] += 1

		Aligner.log.debug(f'fullAlignments: {len(self._fullAlignments)}')
		Aligner.log.debug(f'wordAlignments: {len(self._wordAlignments)}')
		Aligner.log.debug(f'readCounts: {len(self._readCounts)}')

		return self._fullAlignments, self._wordAlignments, self._readCounts

import collections
import difflib
import logging
from typing import Counter, DefaultDict, Dict, List, Optional, Tuple

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
		for original, gold, token in progressbar.progressbar(tokens.consolidated, max_value=len(tokens)):
			self._wordAlignments[original][token.index] = gold
			for leftChar, rightChar in zip(original, gold):
				self._fullAlignments.append((leftChar, rightChar))
				self._readCounts[leftChar][rightChar] += 1

		Aligner.log.debug(f'fullAlignments: {len(self._fullAlignments)}')
		Aligner.log.debug(f'wordAlignments: {len(self._wordAlignments)}')
		Aligner.log.debug(f'readCounts: {len(self._readCounts)}')

		return self._fullAlignments, self._wordAlignments, self._readCounts

	def apply_as_gold(self, left: TokenList, right: TokenList):
		"""
		Sets gold on the left tokens based on originals from the right tokens.
		
		Will attempt to handle cases where tokens have been deleted.

		:param left: A TokenList
		:param right: A TokenList
		"""
		
		#junk_check = lambda t: t.is_discarded
		matcher = difflib.SequenceMatcher(a=left, b=right)
		opcodes = matcher.get_opcodes()
		
		for tag, i1, i2, j1, j2 in opcodes:
			if tag == 'equal':
				for token in left[i1:i2]:
					self.log.info(f'Setting gold on {token} to original')
					token.gold = token.original
			elif tag == 'replace':
				for original_token, gold_token in zip(left[i1:i2], right[j1:j2]):
					self.log.info(f'Setting gold on {original_token} to original from {gold_token}')
					original_token.gold = gold_token.original
			elif tag == 'delete':
				for token in left[i1:i2]:
					self.log.info(f'Marking {token} as discarded')
					token.is_discarded = True
			elif tag == 'insert':
				raise ValueError(f'Cannot insert tokens!')
		
				

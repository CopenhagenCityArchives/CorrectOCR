import collections
import logging
from difflib import SequenceMatcher
from typing import Counter, DefaultDict, Dict, List, Optional, Tuple

from ._util import punctuationRE


class Aligner(object):
	log = logging.getLogger(f'{__name__}.Aligner')

	def __init__(self):
		self._fullAlignments: Optional[List[List[str, str]]] = None
		self._wordAlignments: Optional[DefaultDict[str, Dict[int, str]]] = None
		self._readCounts: Optional[DefaultDict[str, Counter[str]]] = None

	def _align_words(self, left: str, right: str):
		(aPos, bPos, aStr, bStr) = (0, 0, '', '')
		#matcher.set_seq1(best.original)
		m = SequenceMatcher(None, left, right)
		for (a, b, c) in m.get_matching_blocks():
			if a > aPos:
				aStr += left[aPos:a]
			if b > bPos:
				bStr += right[bPos:b]
			if len(aStr) > 0 or len(bStr) > 0:
				self._fullAlignments.append([aStr, bStr])
				self._readCounts[aStr][bStr] += 1
			for char in left[a:c]:
				self._fullAlignments.append([char, char])
				self._readCounts[char][char] += 1
			(aPos, bPos, aStr, bStr) = (a+c, b+c, '', '')

	def _align_tokens(self, left: List[str], right: List[str], index: int):
		remove = set()

		for i, left in enumerate(left, index):
			matcher = SequenceMatcher(None, None, left, autojunk=False)
			(best, bestRatio) = (None, 0.0)
			for right in right:
				matcher.set_seq1(right)
				ratio = matcher.ratio()
				if ratio > bestRatio:
					best = right
					bestRatio = ratio
				if ratio == 1.0:
					continue # no reason to compare further
			#Aligner.log.debug(f'\t{left} -> {best} {bestRatio}')
			if best and bestRatio > 0.7 or (len(left) > 4 and bestRatio > 0.6):
				self._align_words(left, best)
				self._wordAlignments[left][i] = best
				remove.add(left)
			else:
				#Aligner.log.debug(f'\tbestRatio: {left} & {best} = {bestRatio}')
				pass
		
		return [t for t in left if t not in remove], right

	def alignments(self, originalTokens: List[str], goldTokens: List[str]):
		"""
		Aligns the original and gold tokens in order to discover the corrections that have been made.

		:param originalTokens: List of original text strings
		:param goldTokens: List of gold text strings
		:return: A tuple with three elements:

		   -  ``fullAlignments`` -- A list of letter-by-letter alignments (2-element tuples)
		   -  ``wordAlignments``--
		   -  ``readCounts`` -- A dictionary of counts of aligned reads for each character.
		"""
		self._fullAlignments: List[Tuple[str, str]] = []
		self._wordAlignments: DefaultDict[str, Dict[int, str]] = collections.defaultdict(dict)
		self._readCounts: DefaultDict[str, Counter[str]] = collections.defaultdict(collections.Counter)
		
		#nopunct = lambda t: not t.is_punctuation()
		#
		#a = list(filter(nopunct, originalTokens))
		#b = list(filter(nopunct, goldTokens))

		a = originalTokens
		b = goldTokens
		
		matcher = SequenceMatcher(isjunk=lambda t: punctuationRE.match(t), autojunk=False)
		matcher.set_seqs(a, b)
		
		leftRest = []
		rightRest = []

		for tag, i1, i2, j1, j2 in matcher.get_opcodes():
			if tag == 'equal':
				for token in a[i1:i2]:
					for char in token:
						self._fullAlignments.append((char, char))
						self._readCounts[char][char] += 1
					self._wordAlignments[token][i1] = token
			elif tag == 'replace':
				if i2-i1 == j2-j1:
					for left, right in zip(a[i1:i2], b[j1:j2]):
						for leftChar, rightChar in zip(left, right):
							self._fullAlignments.append((leftChar, rightChar))
							self._readCounts[leftChar][rightChar] += 1
						self._wordAlignments[left][i1] = right
				else:
					#Aligner.log.debug(f'{tag:7}   a[{i1}:{i2}] --> b[{j1}:{j2}] {a[i1:i2]!r:>8} --> {b[j1:j2]!r}')
					(left, right) = self._align_tokens(a[i1:i2], b[j1:j2], i1)
					leftRest.extend(left)
					rightRest.extend(right)
			elif tag == 'delete':
				leftRest.extend(a[i1:i2])
			elif tag == 'insert':
				rightRest.extend(b[j1:j2])
		
		(left, right) = self._align_tokens(leftRest, rightRest, int(len(a) / 3))
		
		Aligner.log.debug(f'unmatched tokens left {len(left)}: {sorted(left)}')
		Aligner.log.debug(f'unmatched tokens right {len(right)}: {sorted(right)}')
	
		#Aligner.log.debug(f"æ: {self._readCounts['æ']}")
		#Aligner.log.debug(f"cr: {self._readCounts.get('cr', None)}")
		#Aligner.log.debug(f"c: {self._readCounts.get('c', None)}")
		#Aligner.log.debug(f"r: {self._readCounts.get('r', None)}")

		tmpWordAlignments = []
		for i, (left, alignments) in enumerate(self._wordAlignments.items()):
			closest = sorted(alignments.items(), key=lambda x: abs(x[0] - i))
			tmpWordAlignments.append((left, closest[0][1]))

		#Aligner.log.debug(f'tmpWordAlignments: {tmpWordAlignments}')
		#Aligner.log.debug(f'lens: {len(originalTokens)} {len(goldTokens)} {len(tmpWordAlignments)}')

		return self._fullAlignments, self._wordAlignments, self._readCounts

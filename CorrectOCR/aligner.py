import collections
import logging
from difflib import SequenceMatcher
from typing import DefaultDict, Dict, List, Counter

from . import punctuationRE


class Aligner(object):
	log = logging.getLogger(f'{__name__}.Aligner')

	def __init__(self):
		self.fullAlignments: List[List[str, str]] = None
		self.wordAlignments: DefaultDict[str, Dict[int, str]] = None
		self.misreadCounts: DefaultDict[str, Counter[str]] = None

	def align_words(self, left: str, right: str):
		(aPos, bPos, aStr, bStr) = (0, 0, '', '')
		#matcher.set_seq1(best.original)
		m = SequenceMatcher(None, left, right)
		for (a, b, c) in m.get_matching_blocks():
			if a > aPos:
				aStr += left[aPos:a]
			if b > bPos:
				bStr += right[bPos:b]
			if len(aStr) > 0 or len(bStr) > 0:
				self.fullAlignments.append([aStr, bStr])
				self.misreadCounts[aStr][bStr] += 1
			for char in left[a:c]:
				self.fullAlignments.append([char, char])
				self.misreadCounts[char][char] += 1
			(aPos, bPos, aStr, bStr) = (a+c, b+c, '', '')

	def align_tokens(self, left: List[str], right: List[str], index: int):
		remove = set()

		for i, left in enumerate(left, index):
			matcher = SequenceMatcher(None, None, left, autojunk=None)
			(best, bestRatio) = (None, 0.0)
			for right in right:
				matcher.set_seq1(right)
				ratio = matcher.ratio()
				if ratio > bestRatio:
					best = right
					bestRatio = ratio
				if ratio == 1.0:
					continue # no reason to compare further
			if best and bestRatio > 0.7 or (len(left) > 4 and bestRatio > 0.6):
				#Aligner.log.debug(f'\t{left} -> {best} {bestRatio}')
				self.align_words(left, best)
				self.wordAlignments[left][i] = best
				remove.add(left)
			else:
				#Aligner.log.debug(f'\tbestRatio: {left} & {best} = {bestRatio}')
				pass
		
		return [t for t in left if t not in remove], right

	def alignments(self, originalTokens: List[str], goldTokens: List[str]):
		self.fullAlignments: List[List[str, str]] = []
		self.wordAlignments: DefaultDict[str, Dict[int, str]] = collections.defaultdict(dict)
		self.misreadCounts: DefaultDict[str, Counter[str]] = collections.defaultdict(collections.Counter)
		
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
						self.fullAlignments.append([char, char])
						self.misreadCounts[char][char] += 1
					self.wordAlignments[token][i1] = token
			elif tag == 'replace':
				if i2-i1 == j2-j1:
					for left, right in zip(a[i1:i2], b[j1:j2]):
						for leftChar, rightChar in zip(left, right):
							self.fullAlignments.append([leftChar, rightChar])
							self.misreadCounts[leftChar][rightChar] += 1
						self.wordAlignments[left][i1] = right
				else:
					#Aligner.log.debug(f'{tag:7}   a[{i1}:{i2}] --> b[{j1}:{j2}] {a[i1:i2]!r:>8} --> {b[j1:j2]!r}')
					(left, right) = self.align_tokens(a[i1:i2], b[j1:j2], i1)
					leftRest.extend(left)
					rightRest.extend(right)
			elif tag == 'delete':
				leftRest.extend(a[i1:i2])
			elif tag == 'insert':
				rightRest.extend(b[j1:j2])
		
		(left, right) = self.align_tokens(leftRest, rightRest, int(len(a)/3))
		
		Aligner.log.debug(f'unmatched tokens left {len(left)}: {sorted(left)}')
		Aligner.log.debug(f'unmatched tokens right {len(right)}: {sorted(right)}')
	
		#Aligner.log.debug(f"æ: {self.misreadCounts['æ']}")
		#Aligner.log.debug(f"cr: {self.misreadCounts.get('cr', None)}")
		#Aligner.log.debug(f"c: {self.misreadCounts.get('c', None)}")
		#Aligner.log.debug(f"r: {self.misreadCounts.get('r', None)}")
		
		return self.fullAlignments, self.wordAlignments, self.misreadCounts

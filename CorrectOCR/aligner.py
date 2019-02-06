import logging
import collections

from difflib import SequenceMatcher

class Aligner(object):
	def __init__(self):
		self.log = logging.getLogger(f'{__name__}.align')

	def align_words(self, left, right, index):
		(aPos, bPos, aStr, bStr) = (0, 0, '', '')
		#matcher.set_seq1(best.original)
		m = SequenceMatcher(None, left, right)
		for (a,b,c) in m.get_matching_blocks():
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

	def align_tokens(self, left, right, index):
		remove = set()
		
		for i, leftToken in enumerate(left, index):
			matcher = SequenceMatcher(None, None, leftToken.original, autojunk=None)
			(best, bestRatio) = (None, 0.0)
			for rightToken in right:
				matcher.set_seq1(rightToken.original)
				ratio = matcher.ratio()
				if ratio > bestRatio:
					best = rightToken
					bestRatio = ratio
				if ratio == 1.0:
					continue # no reason to compare further
			if best and bestRatio > 0.7 or (len(leftToken.original) > 4 and bestRatio > 0.6):
				#self.log.debug(f'\t{leftToken} -> {best} {bestRatio}')
				self.align_words(leftToken.original, best.original, i)
				self.wordAlignments[leftToken.original][i] = best.original
				remove.add(leftToken)
			else:
				#self.log.debug(f'\tbestRatio: {leftToken} & {best} = {bestRatio}')
				pass
		
		return [t for t in left if t not in remove], right

	def alignments(self, originalTokens, goldTokens, force=False):
		self.fullAlignments = []
		self.wordAlignments = collections.defaultdict(dict)
		self.misreadCounts = collections.defaultdict(collections.Counter)
		
		#nopunct = lambda t: not t.is_punctuation()
		#
		#a = list(filter(nopunct, originalTokens))
		#b = list(filter(nopunct, goldTokens))

		a = originalTokens
		b = goldTokens
		
		matcher = SequenceMatcher(isjunk=lambda t: t.is_punctuation(), autojunk=False)
		matcher.set_seqs(a, b)
		
		leftRest = []
		rightRest = []
		
		for tag, i1, i2, j1, j2 in matcher.get_opcodes():
			if tag == 'equal':
				for token in a[i1:i2]:
					for char in token.original:
						self.fullAlignments.append([char, char])
						self.misreadCounts[char][char] += 1
				self.wordAlignments[token.original][i1] = token.original
			elif tag == 'replace':
				if i2-i1 == j2-j1:
					for leftToken, rightToken in zip(a[i1:i2], b[j1:j2]):
						for leftChar, rightChar in zip(leftToken.original, rightToken.original):
							self.fullAlignments.append([leftChar, rightChar])
							self.misreadCounts[leftChar][rightChar] += 1
						self.wordAlignments[leftToken.original][i1] = rightToken.original
				else:
					#self.log.debug(f'{tag:7}   a[{i1}:{i2}] --> b[{j1}:{j2}] {a[i1:i2]!r:>8} --> {b[j1:j2]!r}')
					(left, right) = self.align_tokens(a[i1:i2], b[j1:j2], i1)
					leftRest.extend(left)
					rightRest.extend(right)
			elif tag == 'delete':
				leftRest.extend(a[i1:i2])
			elif tag == 'insert':
				rightRest.extend(b[j1:j2])
		
		(left, right) = self.align_tokens(leftRest, rightRest, int(len(a)/3))
		
		#self.log.debug(f'unmatched tokens left {len(left)}: {sorted(left)}')
		#self.log.debug(f'unmatched tokens right {len(right)}: {sorted(right)}')
	
		#self.log.debug(f"æ: {self.misreadCounts['æ']}")
		#self.log.debug(f"cr: {self.misreadCounts.get('cr', None)}")
		#self.log.debug(f"c: {self.misreadCounts.get('c', None)}")
		#self.log.debug(f"r: {self.misreadCounts.get('r', None)}")
		
		return (self.fullAlignments, self.wordAlignments, self.misreadCounts)

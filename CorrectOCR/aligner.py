import json
import logging

import collections

from . import open_for_reading
from .tokenizer import tokenize_path


class Aligner(object):
	def __init__(self, originalPath, goldPath, trainingPath):
		self.originalPath = originalPath
		self.goldPath = goldPath
		self.trainingPath = trainingPath
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

	def alignments(self, fileid, force=False):
		self.fullAlignments = []
		self.wordAlignments = collections.defaultdict(dict)
		self.misreadCounts = collections.defaultdict(collections.Counter)
		
		faPath = self.trainingPath.joinpath(f'{fileid}_fullAlignments.json')
		waPath = self.trainingPath.joinpath(f'{fileid}_wordAlignments.json')
		mcPath = self.trainingPath.joinpath(f'{fileid}_misreadCounts.json')
		
		if not force and (faPath.is_file() and waPath.is_file() and mcPath.is_file()):
			# presume correctness, user may clean the files to rerun
			self.log.info(f'Alignment files for {fileid} exist, will read and return. Use --force or clean files to rerun a subset.')
			return (
				json.load(open_for_reading(faPath)),
				{o: {int(k): v for k,v in i.items()} for o, i in json.load(open_for_reading(waPath)).items()},
				json.load(open_for_reading(mcPath))
			)
		if force:
			self.log.info(f'Creating alignment files for {fileid}')
		
		originalFile = self.originalPath.joinpath(f'{fileid}.txt')
		goldFile = self.goldPath.joinpath(f'{fileid}.txt')

		#nopunct = lambda t: not t.is_punctuation()
		#
		#a = list(filter(nopunct, tokenize_path(originalFile)))
		#b = list(filter(nopunct, tokenize_path(goldFile)))

		a = tokenize_path(originalFile)
		b = tokenize_path(goldFile)
		
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
	
		with open(faPath, 'w', encoding='utf-8') as f:
			json.dump(self.fullAlignments, f)
			f.close()

		with open(waPath, 'w', encoding='utf-8') as f:
			json.dump(self.wordAlignments, f)
			self.log.debug(self.wordAlignments)
			f.close()
		
		with open(mcPath, 'w', encoding='utf-8') as f:
			json.dump(self.misreadCounts, f)
			f.close()
		
		#self.log.debug(f"æ: {self.misreadCounts['æ']}")
		#self.log.debug(f"cr: {self.misreadCounts.get('cr', None)}")
		#self.log.debug(f"c: {self.misreadCounts.get('c', None)}")
		#self.log.debug(f"r: {self.misreadCounts.get('r', None)}")
		
		return (self.fullAlignments, self.wordAlignments, self.misreadCounts)


def align(config):
	a = Aligner(config.originalPath, config.goldPath, config.trainingPath)
	if config.fileid:
		a.alignments(config.fileid, force=config.force)
	elif config.allPairs:
		for goldFile in config.goldPath.iterdir():
			basename = goldFile.stem
			a.alignments(basename, force=config.force)


def get_alignments(fileid, config, force=False):
	a = Aligner(config.originalPath, config.goldPath, config.trainingPath)

	return a.alignments(fileid, force=force)

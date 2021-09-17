import unittest

from .mocks import *

from CorrectOCR.aligner import Aligner
from CorrectOCR.tokens import Tokenizer


class TestAligner(unittest.TestCase):
	def test_alignments(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'))

		f = MockCorpusFile('This is a t3st')
		tokens = t.tokenize(f, MockConfig())
		
		tokens[0].gold = tokens[0].original
		tokens[1].gold = tokens[1].original
		tokens[2].gold = tokens[2].original
		tokens[3].gold = 'test'
		
		aligner = Aligner()
		
		(fullAlignments, wordAlignments, readCounts) = aligner.alignments(tokens)
		
		# TODO more tests:
		# [('T', 'T'), ('h', 'h'), ('i', 'i'), ('s', 's'), ('i', 'i'), ('s', 's'), ('a', 'a'), ('t', 't'), ('3', 'e'), ('s', 's'), ('t', 't')]
		# defaultdict(<class 'dict'>, {'This': {0: 'This'}, 'is': {1: 'is'}, 'a': {2: 'a'}, 't3st': {3: 'test'}})
		# defaultdict(<class 'collections.Counter'>, {'T': Counter({'T': 1}), 'h': Counter({'h': 1}), 'i': Counter({'i': 2}), 's': Counter({'s': 3}), 'a': Counter({'a': 1}), 't': Counter({'t': 2}), '3': Counter({'e': 1})})
		self.assertEqual(readCounts['3']['e'], 1, f'The character 3 should have been read as e exactly once: {readCounts}')

	def test_align_gold(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'))

		left = t.tokenize(MockCorpusFile('This is a t3st'), MockConfig())
		right = t.tokenize(MockCorpusFile('This is a test'), MockConfig())
		
		aligner = Aligner()
		
		aligner.apply_as_gold(left, right)

		for l, r in zip(left, right):
			self.assertEqual(l.gold, r.original, f'{l} should have gold from {r}')

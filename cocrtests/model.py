import unittest

from .mocks import *

from CorrectOCR.model.hmm import HMM, HMMBuilder
from CorrectOCR.tokens import Tokenizer


class TestModel(unittest.TestCase):
	def setUp(self):
		dictionary = set(["String"])

		readCounts = {
			"S": { "S": 1000},
			"t": { "t": 999, "l": 1},
			"r": { "r": 1000},
			"i": { "i": 1000},
			"n": { "n": 1000},
			"g": { "g": 1000},
			"-": { "-": 1000},
			"\xad": { "\xad": 1000},
			"(": { ")": 1000},
			"(": { ")": 1000},
		}
		gold_words = ["String"]

		builder = HMMBuilder(dictionary, 0.0001, 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz()-\xad', readCounts, [], gold_words)

		self.hmm = HMM(None, None, use_cache=False)
		self.hmm.init = builder.init
		self.hmm.tran = builder.tran
		self.hmm.emis = builder.emis


	def test_kbest_regular(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'))

		f = MockCorpusFile('Slring')
		tokens = t.tokenize(f, MockConfig(type='fs'))

		self.hmm.generate_kbest(tokens)

		self.assertEqual(tokens[0].kbest[1].candidate, 'String', f'The first candidate should be "String": {tokens[0]}')


	def test_kbest_hyphenated(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'))

		f = MockCorpusFile('Str-ing')
		tokens = t.tokenize(f, MockConfig(type='fs'))

		self.hmm.generate_kbest(tokens)

		self.assertEqual(tokens[0].kbest[1].candidate, 'Str-ing', f'The first candidate should be "Str-ing": {tokens[0]}')


	def test_kbest_soft_hyphen(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'))

		f = MockCorpusFile('Str\xading')
		tokens = t.tokenize(f, MockConfig(type='fs'))

		self.hmm.generate_kbest(tokens)

		self.assertEqual(tokens[0].kbest[1].candidate, 'Str\xading', f'The first candidate should be "Str\xading": {tokens[0]}')


	def test_kbest_parens(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'))

		f = MockCorpusFile('(String)')
		tokens = t.tokenize(f, MockConfig(type='fs'))

		self.hmm.generate_kbest(tokens)

		self.assertEqual(tokens[0].kbest[1].candidate, '(String)', f'The first candidate should be "(String)": {tokens[0]}')

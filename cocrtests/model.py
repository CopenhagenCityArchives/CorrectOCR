import unittest

from .mocks import *

from CorrectOCR.model.hmm import HMM, HMMBuilder
from CorrectOCR.tokens import Tokenizer


class TestModel(unittest.TestCase):
	def setUp(self):
		gold_words = ['String', 'Stræng']
		dictionary = set(gold_words)

		readCounts = {
			"S": { "S": 1000},
			"t": { "t": 999, "l": 1},
			"r": { "r": 1000},
			"i": { "i": 1000},
			"æ": { "æ": 1000},
			"n": { "n": 1000},
			"g": { "g": 1000},
			"-": { "-": 1000},
			"\xad": { "\xad": 1000},
			"(": { ")": 1000},
			"(": { ")": 1000},
		}

		builder = HMMBuilder(dictionary, 0.0001, 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz()-\xad', readCounts, [], gold_words)

		self.hmm = HMM(None, None, use_cache=False)
		self.hmm.init = builder.init
		self.hmm.tran = builder.tran
		self.hmm.emis = builder.emis


	def test_kbest_regular(self):
		kbest = self.hmm.kbest_for_word('Slring', 4)
		self.assertEqual(kbest[1].candidate, 'String', f'The first candidate should be "String": {kbest}')


	def test_kbest_hyphenated(self):
		kbest = self.hmm.kbest_for_word('Str-ing', 4)
		self.assertEqual(kbest[1].candidate, 'Str-ing', f'The first candidate should be "Str-ing": {kbest}')


	def test_kbest_soft_hyphen(self):
		kbest = self.hmm.kbest_for_word('Str\xading', 4)
		self.assertEqual(kbest[1].candidate, 'Str\xading', f'The first candidate should be "Str\xading": {kbest}')


	def test_kbest_parens(self):
		kbest = self.hmm.kbest_for_word('(String)', 4)
		self.assertEqual(kbest[1].candidate, '(String)', f'The first candidate should be "(String)": {kbest}')


	def test_multichars(self):
		self.hmm.multichars = {
			'ce': ['æ'],
		}

		kbest = self.hmm.kbest_for_word('Strceng', 4)
		self.assertEqual(kbest[1].candidate, 'Stræng', f'The first candidate should be "Stræng": {kbest}')
		
		# reset to avoid touching other tests
		self.hmm.multichars = None
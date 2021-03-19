import unittest

from .mocks import *

from CorrectOCR.model.hmm import HMM, HMMBuilder
from CorrectOCR.tokens import Tokenizer


class TestModel(unittest.TestCase):
	def test_kbest(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'))

		f = MockCorpusFile('Slring')
		tokens = t.tokenize(f, MockConfig(type='fs'))
		token = tokens[0]

		dictionary = set(["String"])

		readCounts = {
			"S": { "S": 1000},
			"t": { "l": 1000},
			"r": { "r": 1000},
			"i": { "i": 1000},
			"n": { "n": 1000},
			"g": { "g": 1000},
		}
		gold_words = ["String"]

		builder = HMMBuilder(dictionary, 0.0001, 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz', readCounts, [], gold_words)

		hmm = HMM(None, None, use_cache=False)
		hmm.init = builder.init
		hmm.tran = builder.tran
		hmm.emis = builder.emis

		hmm.generate_kbest(tokens)

		self.assertEqual(token.kbest[1].candidate, 'String', f'The first candidate should be "String".')

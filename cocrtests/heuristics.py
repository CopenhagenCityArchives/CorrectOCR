import unittest

from .mocks import *

from CorrectOCR.heuristics import Heuristics
from CorrectOCR.model.kbest import KBestItem
from CorrectOCR.tokens import Tokenizer


class TestHeuristics(unittest.TestCase):
	def test_auto_dehyphenation(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'))

		f = MockCorpusFile('String')
		tokens = t.tokenize(f, MockConfig())
		token = tokens[0]

		self.assertIsNone(token.bin, f'Token should not be in any bin.')
		
		token.kbest = {
			1: KBestItem("String", 1.0),
		}

		dictionary = set(["String"])
		settings = {
			1: "o",
		}
		heuristics = Heuristics(settings, dictionary)
		
		heuristics.bin_tokens(tokens)

		self.assertEqual(token.bin.number, 1, f'Token should be in bin 1.')

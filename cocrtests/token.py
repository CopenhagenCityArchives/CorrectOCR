import unittest

from .mocks import *

from CorrectOCR.tokens import Tokenizer


class TestToken(unittest.TestCase):
	def test_tokenizer(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'))

		f = MockCorpusFile('String')
		tokens = t.tokenize(f, MockConfig())

		self.assertEqual(len(tokens), 1, f'There should be 1 token.')

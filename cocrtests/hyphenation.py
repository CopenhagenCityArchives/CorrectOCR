import unittest

from .mocks import *

from CorrectOCR._util import hyphenRE
from CorrectOCR.tokens import Tokenizer


class TestHyphenation(unittest.TestCase):
	def test_hyphenation_regex(self):
		self.assertTrue(hyphenRE.search('abc-'), '"abc-" should match.')
		self.assertFalse(hyphenRE.search('abc-def'), '"abc-def" should NOT match.')

	def test_auto_dehyphenation(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'))

		f = MockCorpusFile('Str- ing Te-st')
		tokens = t.tokenize(f, MockConfig(type='fs'))
		tokens.dehyphenate()

		self.assertEqual(str(tokens), 'String Te-st', f'Resulting string should be dehyphenated in {tokens}.')

	def test_manual_dehyphenation(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'))

		f = MockCorpusFile('Str- ing')
		tokens = t.tokenize(f, MockConfig(type='fs'))

		self.assertEqual(str(tokens), 'Str- ing', f'Resulting string should not be dehyphenated.')

		tokens[0].is_hyphenated = True

		self.assertEqual(str(tokens), 'String', f'Resulting string should be dehyphenated.')

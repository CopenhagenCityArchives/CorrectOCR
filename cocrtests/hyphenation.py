import unittest

from .mocks import *

from CorrectOCR._util import hyphenRE
from CorrectOCR.tokens import Tokenizer


class TestHyphenation(unittest.TestCase):
	def test_hyphenation_regex(self):
		self.assertTrue(hyphenRE.search('abc-'), '"abc-" should match.')
		self.assertTrue(hyphenRE.search('Politi\u00ad'), '"Politi\u00ad" should match.')
		self.assertTrue(hyphenRE.search('Politi\xad'), '"Politi\xad" should match.')
		self.assertFalse(hyphenRE.search('abc-def'), '"abc-def" should NOT match.')
		self.assertFalse(hyphenRE.search('Nørreherred'), '"Nørreherred" should NOT match.')

	def test_auto_dehyphenation_hard(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'))

		f = MockCorpusFile('Str- ing Te-st')
		tokens = t.tokenize(f, MockConfig())
		tokens.dehyphenate()

		self.assertEqual(str(tokens), 'String Te-st', f'Resulting string should be dehyphenated in {tokens}.')

	def test_auto_dehyphenation_soft(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'))

		f = MockCorpusFile('Str\xad ing Te\xadst')
		tokens = t.tokenize(f, MockConfig())
		tokens.dehyphenate()

		self.assertEqual(str(tokens), 'String Te\xadst', f'Resulting string should be dehyphenated in {tokens}.')

	def test_manual_dehyphenation(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'))

		f = MockCorpusFile('Str- ing')
		tokens = t.tokenize(f, MockConfig())

		self.assertEqual(str(tokens), 'Str- ing', f'Resulting string should not be dehyphenated.')

		tokens[0].is_hyphenated = True

		self.assertEqual(str(tokens), 'String', f'Resulting string should be dehyphenated.')

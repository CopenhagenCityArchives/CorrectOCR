import unittest

from .mocks import *

from CorrectOCR.tokens import Tokenizer


class TestLastModified(unittest.TestCase):
	def test_last_modified(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'))

		f = MockCorpusFile('test')
		tokens = t.tokenize(f, MockConfig())
		token = tokens[0]
		
		token.gold = token.original
		self.assertEqual(token.gold, token.original, f'Resulting token.gold should be identical with original: {vars(token)}')
		self.assertFalse(token.is_discarded, f'Resulting token should not be discarded: {vars(token)}')
		last_modified = token.last_modified
		
		token.is_discarded = True
		self.assertTrue(token.is_discarded, f'Resulting token should be discarded: {vars(token)}')
		self.assertEqual(token.gold, '', f'Resulting token.gold should be cleared: {vars(token)}')
		
		self.assertTrue(token.last_modified > last_modified, f'Resulting token should have updated last_modified ({last_modified} > {token.last_modified}): {vars(token)}')

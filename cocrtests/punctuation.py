import unittest

from .mocks import *

from CorrectOCR.tokens import Tokenizer


class TestPunctuation(unittest.TestCase):
	def test_punctuation(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'))

		f = MockCorpusFile('(test)')
		tokens = t.tokenize(f, MockConfig(type='fs'))
		token = tokens[0]
		
		self.assertEqual(token.original, '(test)', f'Resulting token.original should be identical with original string: {vars(token)}')
		self.assertEqual(token.normalized, 'test', f'Resulting token.normalized should be identical with original string without parentheses: {vars(token)}')

		token.gold = 'test'
		self.assertEqual(token.gold, 'test', f'Resulting token.gold should be identical with original string without parentheses: {vars(token)}')

		token.gold = '(test)'
		self.assertEqual(token.gold, '(test)', f'Resulting token.gold should be identical with original string: {vars(token)}')

import unittest

from .mocks import *

from CorrectOCR.tokens import Token, Tokenizer


class TestToken(unittest.TestCase):
	def test_tokenizer(self):
		t = Tokenizer.for_type('.txt')(language=MockLang('english'))

		f = MockCorpusFile('String')
		tokens = t.tokenize(f, MockConfig())

		self.assertEqual(len(tokens), 1, f'There should be 1 token.')

	def test_from_to_dict(self):
		d = {
			'token_type': 'PDFToken',
			'token_info': None,
			'annotations': [],
			'bin': None,
			'decision': None,
			'docid': 'abc',
			'gold': None,
			'has_error': False,
			'image_url': '/images/abc/3.png',
			'index': 3,
			'is_discarded': False,
			'is_hyphenated': False,
			'kbest': {'1': {'candidate': 'ti-me', 'probability': 1.0}},
			'last_modified': None,
			'original': 'ti-',
			'selection': None,
		}
		
		t = Token.from_dict(d)
		
		self.assertEqual(t.to_dict(), d, f'The token should be identical to its dictionary and vice versa: {t} != {d}')

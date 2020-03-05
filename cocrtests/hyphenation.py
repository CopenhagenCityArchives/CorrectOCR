import unittest
from unittest.mock import mock_open

import logging
import sys

from .mocks import *

from CorrectOCR.tokens import Tokenizer


class TestHyphenation(unittest.TestCase):
	def setUp(self):
		logging.basicConfig(
			stream=sys.stderr,
			format='%(asctime)s - %(levelname)8s - %(name)s - %(message)s',
			level=logging.DEBUG,
		)
		logging.debug('Debug logging active.')

	def test_auto_dehyphenation(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'), dehyphenate=True)

		f = MockCorpusFile('Str- ing')
		tokens = t.tokenize(f, MockConfig(type='fs'))

		self.assertEqual(str(tokens), 'String', f'Resulting string should be dehyphenated.')

	def test_manual_dehyphenation(self):
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'), dehyphenate=False)

		f = MockCorpusFile('Str- ing')
		tokens = t.tokenize(f, MockConfig(type='fs'))

		tokens[0].is_hyphenated = True

		self.assertEqual(str(tokens), 'String', f'Resulting string should be dehyphenated.')

import unittest
from unittest.mock import mock_open

import logging
import pathlib
import sys

from .mocks import *

from CorrectOCR.tokens import Tokenizer


class TestPDF(unittest.TestCase):
	def test_pdf_tokenization(self):
		t = Tokenizer.for_extension('.pdf')(language=MockLang('english'), dehyphenate=False)

		f = pathlib.Path(__file__).parent.joinpath('test.pdf')
		tokens = t.tokenize(f, MockConfig(type='fs'))

		self.assertEqual(str(tokens), 'Once upen a ti- me.', f'Resulting string does not contain expected tokens')

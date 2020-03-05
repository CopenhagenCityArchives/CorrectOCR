import unittest

import logging
import pathlib
import sys

from .mocks import *

from CorrectOCR.__main__ import setup
from CorrectOCR.server import create_app
from CorrectOCR.tokens import Tokenizer

class ServerTests(unittest.TestCase):
	def setUp(self):
		logging.basicConfig(
			stream=sys.stderr,
			format='%(asctime)s - %(levelname)8s - %(name)s - %(message)s',
			level=logging.DEBUG,
		)
		logging.debug('Debug logging active.')

	def setUp(self):
		self.workspace = MockWorkspace(
			root=pathlib.Path('.').resolve(),
			docid='abc',
			words=['Once', 'upen', 'a', 'time']
		)
		self.config = MockConfig(k=4)

		self.app = create_app(self.workspace, self.config).test_client()

	def test_index(self):
		response = self.app.get('/', follow_redirects=True)
		self.assertEqual(response.status_code, 200)

		self.assertEqual(len(response.json), len(self.workspace.docids_for_ext('.pdf')))

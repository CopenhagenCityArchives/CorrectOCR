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
			level=logging.INFO,
		)
		logging.debug('If this text is visible, debug logging is active.')

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

	def test_docview(self):
		response = self.app.get('/abc/tokens.json', follow_redirects=True)
		
		self.assertEqual(len(response.json), 4)
		self.assertTrue(response.json[0]['is_corrected'])
		self.assertFalse(response.json[1]['is_corrected'])

	def test_tokenview(self):
		response = self.app.get('/abc/token-0.json', follow_redirects=True)
		self.assertEqual(response.json['original'], 'Once')
		self.assertEqual(response.json['gold'], 'Once')

		response = self.app.get('/abc/token-1.json', follow_redirects=True)
		self.assertEqual(response.json['original'], 'upen')
		self.assertEqual(response.json['gold'], None)
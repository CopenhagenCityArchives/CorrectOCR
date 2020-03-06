import unittest

import logging
import pathlib
import re
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
		self.assertEqual(response.json[0]['count'], 4)
		self.assertEqual(response.json[0]['corrected'], 1)

	def test_doc_view(self):
		response = self.app.get('/abc/tokens.json', follow_redirects=True)
		
		self.assertEqual(len(response.json), 4)
		self.assertTrue(response.json[0]['is_corrected'])
		self.assertFalse(response.json[1]['is_corrected'])

	def test_token_view(self):
		response = self.app.get('/abc/token-0.json', follow_redirects=True)
		self.assertEqual(response.json['original'], 'Once')
		self.assertEqual(response.json['gold'], 'Once')

		response = self.app.get('/abc/token-1.json', follow_redirects=True)
		self.assertEqual(response.json['original'], 'upen')
		self.assertEqual(response.json['gold'], None)

	def test_token_update(self):
		response = self.app.get('/', follow_redirects=True)
		self.assertEqual(response.json[0]['corrected'], 1)
	
		response = self.app.get('/abc/token-1.json', follow_redirects=True)
		self.assertEqual(response.json['original'], 'upen')
		self.assertEqual(response.json['gold'], None)

		response = self.app.post('/abc/token-1.json', data={'gold': 'upon'}, follow_redirects=True)
		self.assertEqual(response.json['original'], 'upen')
		self.assertEqual(response.json['gold'], 'upon')

		response = self.app.get('/', follow_redirects=True)
		self.assertEqual(response.json[0]['corrected'], 2)
	
	def test_random(self):
		response = self.app.get('/random', follow_redirects=False)
		self.assertEqual(response.status_code, 302)
		
		location_matcher = re.compile(r'^http://localhost/([^/]+)/token-(\d+)\.json$')
		self.assertTrue(location_matcher.match(response.location), f'{location_matcher} should match {response.location}')
		
		response = self.app.get(response.location, follow_redirects=False)
		self.assertEqual(response.status_code, 200)

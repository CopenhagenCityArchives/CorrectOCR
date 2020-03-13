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
			contents='Once upen a ti- me'
		)
		self.config = MockConfig(k=4)

		self.app = create_app(self.workspace, self.config)
		self.app.logger.setLevel(logging.getLogger().getEffectiveLevel())
		self.client = self.app.test_client()

	def test_index(self):
		response = self.client.get('/', follow_redirects=True)
		self.assertEqual(len(response.json), len(self.workspace.docids_for_ext('.pdf')))
		self.assertEqual(response.json[0]['count'], 5, f'Incorrect response: {response.json}')
		self.assertEqual(response.json[0]['corrected'], 1, f'Incorrect response: {response.json}')

	def test_doc_view(self):
		response = self.client.get('/abc/tokens.json', follow_redirects=True)
		self.assertEqual(len(response.json), 5, f'Incorrect response: {response.json}')
		self.assertTrue(response.json[0]['is_corrected'], f'Incorrect response: {response.json}')
		self.assertFalse(response.json[1]['is_corrected'], f'Incorrect response: {response.json}')

	def test_token_view(self):
		response = self.client.get('/abc/token-0.json', follow_redirects=True)
		logging.debug(f'response: {response.json}')
		self.assertEqual(response.json['Original'], 'Once', f'Incorrect response: {response.json}')
		self.assertEqual(response.json['Gold'], 'Once', f'Incorrect response: {response.json}')

		response = self.client.get('/abc/token-1.json', follow_redirects=True)
		self.assertEqual(response.json['Original'], 'upen', f'Incorrect response: {response.json}')
		self.assertEqual(response.json['Gold'], '', f'Incorrect response: {response.json}')

	def test_token_update(self):
		response = self.client.get('/', follow_redirects=True)
		self.assertEqual(response.json[0]['corrected'], 1, f'Incorrect response: {response.json}')
	
		response = self.client.get('/abc/token-1.json', follow_redirects=True)
		self.assertEqual(response.json['Original'], 'upen', f'Incorrect response: {response.json}')
		self.assertEqual(response.json['Gold'], '', f'Incorrect response: {response.json}')

		response = self.client.post('/abc/token-1.json', data={'gold': 'upon'}, follow_redirects=True)
		self.assertEqual(response.json['Original'], 'upen', f'Incorrect response: {response.json}')
		self.assertEqual(response.json['Gold'], 'upon', f'Incorrect response: {response.json}')

		response = self.client.get('/', follow_redirects=True)
		self.assertEqual(response.json[0]['corrected'], 2, f'Incorrect response: {response.json}')

	def test_token_hyphenate_left(self):
		response = self.client.get('/abc/token-3.json', follow_redirects=True)
		self.assertFalse(response.json['Hyphenated'], f'Incorrect response: {response.json}')
		response = self.client.get('/abc/token-4.json', follow_redirects=True)
		self.assertFalse(response.json['Hyphenated'], f'Incorrect response: {response.json}')

		response = self.client.post('/abc/token-4.json', data={'hyphenate': 'left'}, follow_redirects=True)
		self.assertFalse(response.json['Hyphenated'], f'Incorrect response: {response.json}')
		response = self.client.get('/abc/token-3.json', follow_redirects=True)
		self.assertTrue(response.json['Hyphenated'], f'Incorrect response: {response.json}')

	def test_token_hyphenate_right(self):
		response = self.client.get('/abc/token-3.json', follow_redirects=True)
		self.assertFalse(response.json['Hyphenated'], f'Incorrect response: {response.json}')

		response = self.client.post('/abc/token-3.json', data={'hyphenate': 'right'}, follow_redirects=True)
		self.assertTrue(response.json['Hyphenated'], f'Incorrect response: {response.json}')
	
	def test_random(self):
		response = self.client.get('/random', follow_redirects=False)
		self.assertEqual(response.status_code, 302, f'Incorrect response: {response.json}')
		
		location_matcher = re.compile(r'^http://localhost/([^/]+)/token-(\d+)\.json$')
		self.assertTrue(location_matcher.match(response.location), f'{location_matcher} should match {response.location}')
		
		response = self.client.get(response.location, follow_redirects=False)
		self.assertEqual(response.status_code, 200, f'Incorrect response: {response.json}')

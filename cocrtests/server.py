import unittest

import re

from .mocks import *

from CorrectOCR.server import create_app


class ServerTests(unittest.TestCase):
	def setUp(self):
		self.workspace = MockWorkspace(
			root=pathlib.Path('.').resolve(),
			docid='abc',
			contents='Once upen a ti- me'
		)
		tokens = self.workspace.docs['abc'].tokens
		tokens[0].gold = tokens[0].original
		tokens[0].decision = 'original'
		tokens[1].decision = 'annotator'

		self.config = MockConfig(k=4)

		self.app = create_app(self.workspace, self.config)
		self.client = self.app.test_client()

	def test_index(self):
		response = self.client.get('/', follow_redirects=True)
		self.assertEqual(len(response.json), len(self.workspace.documents(ext='.pdf')))
		self.assertEqual(response.json[0]['count'], 5, f'There should be 5 tokens: {response.json}')
		self.assertEqual(response.json[0]['corrected'], 1, f'There should be 1 corrected token: {response.json}')
		self.assertEqual(response.json[0]['corrected_by_model'], 1, f'There should be 1 corrected by model token: {response.json}')

	def test_doc_view(self):
		response = self.client.get('/abc/tokens.json', follow_redirects=True)
		self.assertEqual(len(response.json), 5, f'There should be 5 tokens: {response.json}')
		self.assertTrue(response.json[0]['is_corrected'], f'Token at index 0 should be corrected: {response.json}')
		self.assertFalse(response.json[1]['is_corrected'], f'Token at index 0 should NOT be corrected: {response.json}')

	def test_token_view(self):
		response = self.client.get('/abc/token-0.json', follow_redirects=True)
		self.assertEqual(response.json['Original'], 'Once', f'key "Original" should be "Once": {response.json}')
		self.assertEqual(response.json['Gold'], 'Once', f'key "Gold" should be "Once": {response.json}')

		response = self.client.get('/abc/token-1.json', follow_redirects=True)
		self.assertEqual(response.json['Original'], 'upen', f'key "Original" should be "upen": {response.json}')
		self.assertIsNone(response.json['Gold'], f'key "Gold" should be None: {response.json}')

	def test_token_update(self):
		response = self.client.get('/', follow_redirects=True)
		self.assertEqual(response.json[0]['corrected'], 1, f'There should be 1 corrected token: {response.json}')
	
		response = self.client.get('/abc/token-1.json', follow_redirects=True)
		self.assertEqual(response.json['Original'], 'upen', f'key "Original" should be "upen": {response.json}')
		self.assertIsNone(response.json['Gold'], f'key "Gold" should be None: {response.json}')

		response = self.client.post('/abc/token-1.json', json={'gold': 'upon'}, follow_redirects=True)
		self.assertEqual(response.json['Original'], 'upen', f'key "Original" should be "upen": {response.json}')
		self.assertEqual(response.json['Gold'], 'upon', f'key "Original" should be "upon": {response.json}')

		response = self.client.get('/', follow_redirects=True)
		self.assertEqual(response.json[0]['corrected'], 2, f'There should be 2 corrected tokens: {response.json}')

	def test_token_hyphenate_left(self):
		response = self.client.get('/abc/token-3.json', follow_redirects=True)
		self.assertFalse(response.json['Hyphenated'], f'Token should NOT be hyphenated: {response.json}')
		response = self.client.get('/abc/token-4.json', follow_redirects=True)
		self.assertFalse(response.json['Hyphenated'], f'Token should NOT be hyphenated: {response.json}')

		response = self.client.post('/abc/token-4.json', json={'gold': 'ti-me', 'hyphenate': 'left'}, follow_redirects=True)
		self.assertEqual(response.json['Index'], 3, f'Response should be redirected to "main" token: {response.json}')
		self.assertTrue(response.json['Hyphenated'], f'Token should be hyphenated: {response.json}')
		response = self.client.get('/abc/token-3.json', follow_redirects=True)
		self.assertTrue(response.json['Hyphenated'], f'Token should be hyphenated: {response.json}')
		self.assertEqual(response.json['Gold'], 'ti-', f'Token should have first part of hyphenated word: {response.json}')

	def test_token_hyphenate_right(self):
		response = self.client.get('/abc/token-3.json', follow_redirects=True)
		self.assertFalse(response.json['Hyphenated'], f'Token should NOT be hyphenated: {response.json}')

		response = self.client.post('/abc/token-3.json', json={'gold': 'ti-me', 'hyphenate': 'right'}, follow_redirects=True)
		self.assertTrue(response.json['Hyphenated'], f'Token should be hyphenated: {response.json}')
		self.assertEqual(response.json['Gold'], 'ti-', f'Token should have first part of hyphenated word: {response.json}')
	
	def test_random(self):
		response = self.client.get('/random', follow_redirects=False)
		self.assertEqual(response.status_code, 302, f'Response should be 302 redirect: {response.json}')
		
		location_matcher = re.compile(r'^http://localhost/([^/]+)/token-(\d+)\.json$')
		self.assertTrue(location_matcher.match(response.location), f'{location_matcher} should match {response.location}')
		
		response = self.client.get(response.location, follow_redirects=False)
		self.assertEqual(response.status_code, 200, f'Response should be 200 OK: {response.json}')

	def test_stats(self):
		response = self.client.get('/', follow_redirects=True)
		self.assertEqual(len(response.json), len(self.workspace.documents(ext='.pdf')))
		self.assertEqual(response.json[0]['count'], 5, f'There should be 5 tokens: {response.json}')
		self.assertEqual(response.json[0]['corrected'], 1, f'There should be 1 corrected token: {response.json}')
		self.assertEqual(response.json[0]['corrected_by_model'], 1, f'There should be 1 corrected by model token: {response.json}')

		response = self.client.post('/abc/token-1.json', json={'gold': 'upon'}, follow_redirects=True)

		response = self.client.get('/', follow_redirects=True)
		self.assertEqual(response.json[0]['corrected'], 2, f'There should be 2 corrected tokens: {response.json}')
		self.assertEqual(response.json[0]['corrected_by_model'], 1, f'There should be 1 corrected by model token: {response.json}')

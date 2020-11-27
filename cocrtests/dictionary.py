import unittest

from .mocks import *

from CorrectOCR.dictionary import Dictionary


class TestDictionary(unittest.TestCase):
	def test_dictionary(self):
		d = Dictionary()

		self.assertFalse('word' in d, f'{d} should NOT contain "word"')

		d.add(None, 'word')

		self.assertTrue('word' in d, f'{d} should contain "word"')

	def test_strange(self):
		d = Dictionary()
		
		d.add(None, 'word')
		
		words = [
			'123',
			'.',
			'',
			'[word',
		]
		
		for w in words:
			self.assertTrue(w in d, f'{d} should contain "{w}"')


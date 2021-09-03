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
		
		words_ok = [
			'123',
			'.',
			'',
			'[word',
			'word! ',
			' word ',
			'wo\xadrd', # soft hyphen
			'wo-rd', # hard hyphen
		]
		
		for w in words_ok:
			self.assertTrue(w in d, f'{d} should contain "{w}"')

		words_notok = [
			'test',
			'wo!rd',
		]
		
		for w in words_notok:
			self.assertFalse(w in d, f'{d} should NOT contain "{w}"')
		
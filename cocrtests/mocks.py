from unittest.mock import mock_open

import pathlib

from CorrectOCR.tokens import Tokenizer
from CorrectOCR.tokens._text import StringToken


class MockCorpusFile(object):
	def __init__(self, s):
		self.body = s
		self.path = pathlib.Path('file.txt')
		self.id = self.path.stem


class MockLang(object):
	def __init__(self, s):
		self.name = s


class MockConfig(object):
	def __init__(self, type=None, k=None):
		self.type = type
		self.k = k
		self.host = 'localhost'
		self.debug = True


class MockToken(object):
	def __init__(self, docid, index, original, gold):
		self.docid = docid
		self.index = index
		self.original = original
		self.gold = gold

class MockTokenList(object):
	def __init__(self, docid, words):
		self.docid = docid
		self.tokens = [MockToken(docid=self.docid, index=i, original=word, gold=word if i == 0 else None) for i, word in enumerate(words, 0)]

	def __len__(self):
		return len(self.tokens)

	@property
	def corrected_count(self):
		return len([t for t in self.tokens if t.gold])


class MockWorkspace(object):
	def __init__(self, root, docid, words):
		self.root = root
		self.docid = docid
		self.tokens = MockTokenList(docid, words)

	def docids_for_ext(self, ext):
		return [self.docid]
	
	def autocorrectedTokens(self, docid, k):
		return self.tokens

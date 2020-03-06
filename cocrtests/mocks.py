from unittest.mock import Mock

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
		self.auth_endpoint = None


class MockWorkspace(object):
	def __init__(self, root, docid, contents):
		self.root = root
		self.docid = docid
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'), dehyphenate=True)
		f = MockCorpusFile(contents)
		self.tokens = t.tokenize(f, MockConfig(type='mem'))
		self.tokens[0].gold = self.tokens[0].original

	def docids_for_ext(self, ext):
		return [self.docid]
	
	def autocorrectedTokens(self, docid, k):
		return self.tokens

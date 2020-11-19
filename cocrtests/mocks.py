from unittest.mock import Mock

import pathlib

from CorrectOCR.tokens import Tokenizer
from CorrectOCR.tokens._text import StringToken


class MockCorpusFile(object):
	def __init__(self, body, docid='file'):
		self.docid = docid
		self.body = body
		self.path = pathlib.Path(f'{self.docid}.txt')
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


class MockDocument(object):
	def __init__(self, docid, tokens):
		self.docid = docid
		self.tokens = tokens
		self.info_url = None

	def autocorrectedTokens(self, k):
		return self.tokens


class MockWorkspace(object):
	def __init__(self, root, docid, contents):
		self.root = root
		self.docid = docid
		t = Tokenizer.for_extension('.txt')(language=MockLang('english'), dehyphenate=False)
		tokens = t.tokenize( MockCorpusFile(contents, self.docid), MockConfig(type='mem'))
		tokens[0].gold = tokens[0].original
		self.doc = MockDocument(docid, tokens)
		self.docs = {docid: self.doc}

	def docids_for_ext(self, ext, server_ready=None):
		return [self.docid]
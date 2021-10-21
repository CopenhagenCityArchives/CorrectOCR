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
	def __init__(self, k=None):
		self.type = 'mock'
		self.k = k
		self.host = 'localhost'
		self.debug = True
		self.auth_endpoint = None
		self.profile = False
		self.redirect_hyphenated = True
		self.dynamic_images = True


class MockDocument(object):
	def __init__(self, docid, tokens):
		self.docid = docid
		self.tokens = tokens
		self.info_url = None
		self.is_done = False

	def autocorrectedTokens(self, k):
		return self.tokens


class MockWorkspace(object):
	def __init__(self, root, docid, contents):
		self.root = root
		self.docid = docid
		t = Tokenizer.for_type('.txt')(language=MockLang('english'))
		tokens = t.tokenize( MockCorpusFile(contents, self.docid), MockConfig())
		self.doc = MockDocument(docid, tokens)
		self.docs = {docid: self.doc}

	def documents(self, ext: str=None, server_ready=False, is_done=False):
		return {self.docid: self.doc}


from CorrectOCR.tokens.list import TokenList

@TokenList.register('mock')
class MockTokenList(TokenList):
	"""
		This is a TokenList that cannot load or save, ie. it exists only in memory. Its purpose is to facilitate testing, and should not be used for anything important.
	"""
	def load(self):
		pass

	def save(self, token: 'Token' = None):
		if token:
			self[token.index] = token

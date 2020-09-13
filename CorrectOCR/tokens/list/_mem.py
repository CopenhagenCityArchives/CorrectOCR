import logging

from ._super import TokenList

@TokenList.register('mem')
class MemTokenList(TokenList):
	"""
		This is a TokenList that cannot load or save, ie. it exists only in memory. Its purpose is to facilitate testing, and should not be used for anything important.
	"""
	log = logging.getLogger(f'{__name__}.MemTokenList')

	def load(self, docid: str, kind: str):
		pass

	def save(self, kind: str = None, token: 'Token' = None):
		self.log.debug(f'self.tokens: {self.tokens}')
		self.log.debug(f'token: {vars(token)}')
		if token:
			self[token.index] = token
		self.log.debug(f'self.tokens: {self.tokens}')

	@staticmethod
	def exists(config, docid: str, kind: str):
		return False

	@staticmethod
	def all_tokens(config, docid):
		return self.tokens

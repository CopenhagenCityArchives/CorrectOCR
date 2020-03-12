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
		pass

	@staticmethod
	def exists(config, docid: str, kind: str):
		return False

	@property
	def corrected_count(self):
		return len([t for t in self if t.gold])
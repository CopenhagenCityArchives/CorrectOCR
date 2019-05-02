import logging

from ._super import TokenList

@TokenList.register('fs')
class FSTokenList(TokenList):
	log = logging.getLogger(f'{__name__}.FSTokenList')

	def load(self, path = None):
		from .. import Token
		from ...fileio import FileIO
		self.path = path
		self.log.debug(f'Load from {self.path}')
		for row in FileIO.load(self.path):
			self.append(Token.from_dict(row))

	def save(self, path = None, token = None):
		from ...fileio import FileIO

		self.log.debug(f'Save to {path or self.path}')

		FileIO.save(self, path or self.path)

	@staticmethod
	def _exists(path):
		return path.is_file()
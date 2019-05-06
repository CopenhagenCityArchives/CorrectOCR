import logging

from ._super import TokenList

@TokenList.register('fs')
class FSTokenList(TokenList):
	log = logging.getLogger(f'{__name__}.FSTokenList')

	def load(self, fileid: str, kind: str):
		from .. import Token
		from ...fileio import FileIO
		self.path = path
		self.log.debug(f'Load from {self.path}')
		for row in FileIO.load(self.path):
			self.append(Token.from_dict(row))

	def save(self, kind: str = None, token: 'Token' = None):
		from ...fileio import FileIO

		self.log.debug(f'Save to {path or self.path}')

		FileIO.save(self, path or self.path)

	@staticmethod
	def _exists(self, fileid: str, kind: str):
		path = self.config.trainingPath.joinpath(f'{fileid}.{kind}.csv')
		return path.is_file()
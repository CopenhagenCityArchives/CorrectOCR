import logging

from ._super import TokenList

@TokenList.register('fs')
class FSTokenList(TokenList):
	log = logging.getLogger(f'{__name__}.FSTokenList')

	def load(self, fileid: str, kind: str):
		from .. import Token
		from ...fileio import FileIO
		self.fileid = fileid
		self.kind = kind
		path = self.config.trainingPath.joinpath(f'{fileid}.{kind}.csv')
		self.log.debug(f'Load from {path}')
		for row in FileIO.load(path):
			self.append(Token.from_dict(row))

	def save(self, kind: str = None, token: 'Token' = None):
		from ...fileio import FileIO

		if kind:
			self.kind = kind
		path = self.config.trainingPath.joinpath(f'{self.fileid}.{self.kind}.csv')

		self.log.debug(f'Save to {path}')

		FileIO.save(self, path)

	@staticmethod
	def exists(config, fileid: str, kind: str):
		path = config.trainingPath.joinpath(f'{fileid}.{kind}.csv')

		return path.is_file()
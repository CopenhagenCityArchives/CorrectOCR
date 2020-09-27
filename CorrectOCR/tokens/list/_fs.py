import logging

from ._super import TokenList

@TokenList.register('fs')
class FSTokenList(TokenList):
	log = logging.getLogger(f'{__name__}.FSTokenList')

	def load(self, docid: str):
		from .. import Token
		from ...fileio import FileIO
		self.docid = docid
		path = self.config.trainingPath.joinpath(f'{docid}.csv')
		self.log.debug(f'Load from {path}')
		for row in FileIO.load(path):
			self.tokens.append(Token.from_dict(row))

	def save(self, token: 'Token' = None):
		from ...fileio import FileIO

		path = self.config.trainingPath.joinpath(f'{self.docid}.csv')
		self.log.debug(f'Save to {path}')

		FileIO.save(self, path)

	@staticmethod
	def exists(config, docid: str):
		path = config.trainingPath.joinpath(f'{docid}.csv')

		return path.is_file()

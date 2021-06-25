import logging

from ._super import TokenList

@TokenList.register('fs')
class FSTokenList(TokenList):
	log = logging.getLogger(f'{__name__}.FSTokenList')

	def load(self):
		from .. import Token
		from ...fileio import FileIO
		self.path = FSTokenList._path(self.config, self.docid)
		if self.path.is_file():
			self.log.debug(f'Load from {self.path}')
			for row in FileIO.load(self.path):
				self.tokens.append(Token.from_dict(row))
		FSTokenList.log.debug(f'doc {self.docid} ready for server: {self.server_ready}')

	def save(self, token: 'Token' = None):
		from ...fileio import FileIO

		self.log.debug(f'Save to {self.path}')

		FileIO.save(self, self.path)

	@staticmethod
	def _path(config, docid):
		return config.trainingPath.joinpath(f'{docid}.csv')
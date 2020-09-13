import logging

from ._super import TokenList

@TokenList.register('fs')
class FSTokenList(TokenList):
	log = logging.getLogger(f'{__name__}.FSTokenList')

	def load(self, docid: str, kind: str):
		from .. import Token
		from ...fileio import FileIO
		self.docid = docid
		self.kind = kind
		path = self.config.trainingPath.joinpath(f'{docid}.{kind}.csv')
		self.log.debug(f'Load from {path}')
		for row in FileIO.load(path):
			self.tokens.append(Token.from_dict(row))

	def save(self, kind: str = None, token: 'Token' = None):
		from ...fileio import FileIO

		if kind:
			self.kind = kind

		path = self.config.trainingPath.joinpath(f'{self.docid}.{self.kind}.csv')
		self.log.debug(f'Save to {path}')

		FileIO.save(self, path)

	@staticmethod
	def exists(config, docid: str, kind: str):
		path = config.trainingPath.joinpath(f'{docid}.{kind}.csv')

		return path.is_file()

	@staticmethod
	def all_tokens(config, docid):
		return self.tokens

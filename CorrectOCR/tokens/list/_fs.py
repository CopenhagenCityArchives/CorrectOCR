import logging

from ._super import TokenList

@TokenList.register('fs')
class FSTokenList(TokenList):
	log = logging.getLogger(f'{__name__}.FSTokenList')

	def load(cls, fileid: str, path: str) -> TokenList:
		self.path = path
		log.debug(f'Load from {self.path}')
		from ...fileio import FileIO
		for row in FileIO.load(self.path):
			self.append(Token.from_dict(row))

	def save(self):
		from ...fileio import FileIO

		log.debug(f'Save to {self.path}')

		FileIO.save(self, self.path)
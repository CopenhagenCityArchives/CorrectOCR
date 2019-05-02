from ._super import TokenList

@TokenList.register('fs')
class FSTokenList(TokenList):
	def save(self, name: str):
		from ...fileio import FileIO

		FileIO.save(self, name)
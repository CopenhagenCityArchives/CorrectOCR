import pyodbc

from ._super import TokenList

@TokenList.register('db')
class DBTokenList(TokenList):
	def save(self, name: str):
		connection = pyodbc.connect(self.config.connectionString)
		cursor = connection.cursor()

		for token in self:
			cursor.execute("""
				INSERT OR UPDATE;
			""")

		connection.commit()
		connection.close()

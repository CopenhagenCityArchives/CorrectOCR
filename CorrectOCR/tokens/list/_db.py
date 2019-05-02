import json
import logging
import sys

import pyodbc

from ._super import TokenList


@TokenList.register('db')
class DBTokenList(TokenList):
	log = logging.getLogger(f'{__name__}.DBTokenList')

	@property
	def connection(self):
		return pyodbc.connect(f'driver={{{self.config.db_driver}}};server={self.config.db_host};database={self.config.db};uid={self.config.db_user};pwd={self.config.db_password}')

	def load(self, path=None):
		from .. import Token
		self.path = path
		connection = self.connection
		try:
			with self.connection.cursor() as cursor:
				cursor.execute(
					"SELECT * FROM token WHERE path = ? ORDER BY file_index",
					str(path)
				)
				for result in cursor.fetchall():
					cursor.execute(
						"SELECT * FROM kbest WHERE file_id = ? AND file_index = ? ORDER BY k",
						result.file_id,
						result.file_index
					)
					kbest = cursor.fetchall()
					token_dict = {
						'Token type': result.token_type,
						'Token info': result.token_info,
						'File ID': result.file_id,
						'Index': result.file_index,
						'Gold': result.gold,
						'Bin': result.bin,
						'Heuristic': result.heuristic,
						'Selection': json.loads(result.selection),
						'Decision': result.decision
					}
					for best in kbest:
						token_dict[f"{best.k}-best"] = best.candidate
						token_dict[f"{best.k}-best prob."] = best.probability
					self.append(Token.from_dict(token_dict))
		finally:
			connection.close()

	def save_token(self, path, token):
		self.log.debug(f'saving token {token.fileid}, {token.index}, {token.original}')
		connection = self.connection
		try:
			with connection.cursor() as cursor:
				cursor.execute("""
					REPLACE INTO token (path, file_id, file_index, original, gold, bin, heuristic, decision, selection, token_type, token_info) 
					VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
					""",
					str(path or self.path),
					token.fileid,
					token.index,
					token.original,
					token.gold,
					token.bin.number if token.bin else -1,
					token.bin.heuristic if token.bin else '',
					token.decision,
					json.dumps(token.selection),
					token.__class__.__name__,
					json.dumps(token.token_info)
				)
				if len(token.kbest) > 0:
					cursor.execute(
						"DELETE FROM kbest WHERE file_id = ? AND file_index = ?",
						token.fileid,
						token.index
					)
					for k, item in token.kbest.items():
						cursor.execute("""
							INSERT INTO kbest (file_id, file_index, k, candidate, probability)
							VALUES (?, ?, ?, ?, ?)
							""",
							token.fileid,
							token.index,
							k,
							item.candidate,
							item.probability
						)
			connection.commit()
		finally:
			connection.close()

	def save(self, path = None, token = None):
		if token:
			self.save_token(path, token)
		else:
			for token in self:
				self.save_token(path, token)

	def _exists(self, path):
		connection = self.connection
		try:
			with self.connection.cursor() as cursor:
				cursor.execute(
					"SELECT * FROM token WHERE path = ?",
					str(path)
				)
				return cursor.fetchone() != None
		finally:
			connection.close()


def logging_execute(cursor, sql, *args) :
	run_sql = sql.replace('?', '{!r}').format(*args)
	try:
		logging.info(run_sql)
		cursor.execute(sql, *args)
	except Exception as e:
		logging.error(f'{run_sql} failed with error {e}')

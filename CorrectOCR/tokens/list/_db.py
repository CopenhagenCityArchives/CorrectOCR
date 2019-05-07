from __future__ import annotations

import json
import logging
import weakref

import pyodbc

from ._super import TokenList


@TokenList.register('db')
class DBTokenList(TokenList):
	log = logging.getLogger(f'{__name__}.DBTokenList')

	def __init__(self, *args):
		super().__init__(*args)
		self.connection = pyodbc.connect(f'driver={{{self.config.db_driver}}};server={self.config.db_host};database={self.config.db};uid={self.config.db_user};pwd={self.config.db_password}')
		self.log.debug(f'Opened connection {self.connection}')
		self._finalize = weakref.finalize(self, DBTokenList.close_connection, self)

	def close_connection(self):
		self.log.debug(f'Closing connection {self.connection}')
		self.connection.close()

	def load(self, fileid: str, kind: str):
		from .. import Token
		self.fileid = fileid
		self.kind = kind
		with self.connection.cursor() as cursor:
			cursor.execute("""
				SELECT *
				FROM token
				LEFT JOIN kbest
				ON token.file_id = kbest.file_id AND token.file_index = kbest.file_index
				WHERE token.file_id = ? AND token.kind = ?
				ORDER BY token.file_index, k
				""",
				fileid,
				kind
			)
			token_dict = None
			for result in cursor:
				self.log.debug(f'result: {result}')
				if token_dict and result.file_index != token_dict['Index']:
					self.append(Token.from_dict(token_dict))
					token_dict = None
				if not token_dict:
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
				token_dict[f"{result.k}-best"] = result.candidate
				token_dict[f"{result.k}-best prob."] = result.probability
			self.append(Token.from_dict(token_dict))

	def _save_token(self, token: 'Token'):
		#self.log.debug(f'saving token {token.fileid}, {token.index}, {token.original}, {token.gold}')
		with self.connection.cursor() as cursor:
			cursor.execute("""
				REPLACE INTO token (kind, file_id, file_index, original, gold, bin, heuristic, decision, selection, token_type, token_info) 
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
				""",
				self.kind,
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
		self.connection.commit()

	def save(self, kind: str = None, token: 'Token' = None):
		if kind:
			self.kind = kind
		if token:
			self._save_token(token)
		else:
			for token in self:
				self._save_token(token)

	def _exists(self, fileid: str, kind: str):
		with self.connection.cursor() as cursor:
			cursor.execute(
				"SELECT * FROM token WHERE file_id = ? AND kind = ?",
				fileid,
				kind
			)
			return cursor.fetchone() != None


# for testing:
def logging_execute(cursor, sql, *args) :
	run_sql = sql.replace('?', '{!r}').format(*args)
	try:
		logging.info(run_sql)
		cursor.execute(sql, *args)
	except Exception as e:
		logging.error(f'{run_sql} failed with error {e}')

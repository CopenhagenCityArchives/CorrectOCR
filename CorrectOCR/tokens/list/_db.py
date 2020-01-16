from __future__ import annotations

import json
import logging
import weakref

import progressbar
import pyodbc

from ._super import TokenList


@TokenList.register('db')
class DBTokenList(TokenList):
	log = logging.getLogger(f'{__name__}.DBTokenList')

	def __init__(self, *args):
		super().__init__(*args)
		self.connection = DBTokenList.get_connection(self.config)
		self._finalize = weakref.finalize(self, DBTokenList.close_connection, self)

	def close_connection(self):
		self.log.debug(f'Closing connection {self.connection}')
		self.connection.close()

	def load(self, docid: str, kind: str):
		from .. import Token
		self.docid = docid
		self.kind = kind
		with self.connection.cursor() as cursor:
			cursor.execute("""
				SELECT *
				FROM token
				LEFT JOIN kbest
				ON token.doc_id = kbest.doc_id AND token.doc_index = kbest.doc_index
				WHERE token.doc_id = ? AND token.kind = ?
				ORDER BY token.doc_index, k
				""",
				docid,
				kind
			)
			token_dict = None
			for result in cursor:
				#self.log.debug(f'result: {result}')
				if token_dict and result.doc_index != token_dict['Index']:
					self.append(Token.from_dict(token_dict))
					token_dict = None
				if not token_dict:
					token_dict = {
						'Token type': result.token_type,
						'Token info': result.token_info,
						'Doc ID': result.doc_id,
						'Index': result.doc_index,
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
		#self.log.debug(f'saving token {token.docid}, {token.index}, {token.original}, {token.gold}')
		with self.connection.cursor() as cursor:
			cursor.execute("""
				REPLACE INTO token (kind, doc_id, doc_index, original, gold, bin, heuristic, decision, selection, token_type, token_info) 
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
				""",
				self.kind,
				token.docid,
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
					"DELETE FROM kbest WHERE doc_id = ? AND doc_index = ?",
					token.docid,
					token.index
				)
				for k, item in token.kbest.items():
					cursor.execute("""
						INSERT INTO kbest (doc_id, doc_index, k, candidate, probability)
						VALUES (?, ?, ?, ?, ?)
						""",
						token.docid,
						token.index,
						k,
						item.candidate,
						item.probability
					)
		self.connection.commit()

	def save(self, kind: str = None, token: 'Token' = None):
		DBTokenList.log.info(f'Saving {kind}')
		if kind:
			self.kind = kind
		if token:
			self._save_token(token)
		else:
			for token in progressbar.progressbar(self):
				self._save_token(token)

	@staticmethod
	def exists(config, docid: str, kind: str):
		DBTokenList.log.debug(f'Checking if {kind} for {docid} exist')
		with DBTokenList.get_connection(config).cursor() as cursor:
			cursor.execute(
				"SELECT * FROM token WHERE doc_id = ? AND kind = ? LIMIT 1",
				docid,
				kind
			)
			res = cursor.fetchone()
			DBTokenList.log.debug(f'res: {res}')
			return res is not None

	@staticmethod
	def get_connection(config):
		# TODO global?
		con_str = f'DRIVER={{{config.db_driver}}};SERVER={config.db_host};DATABASE={config.db_name};UID={config.db_user};PWD={config.db_pass}'
		DBTokenList.log.debug(f'Connection string: {con_str}')
		connection = pyodbc.connect(con_str)
		return connection


# for testing:
def logging_execute(cursor, sql, *args) :
	run_sql = sql.replace('?', '{!r}').format(*args)
	try:
		logging.info(run_sql)
		cursor.execute(sql, *args)
	except Exception as e:
		logging.error(f'{run_sql} failed with error {e}')

from __future__ import annotations

import json
import logging
import traceback
import weakref

import pyodbc
import random

from ._super import TokenList

def close_connection(connection):
	logging.getLogger(f'{__name__}.close_connection').debug(f'Closing connection {connection}')
	connection.close()

def get_connection(config):
	log = logging.getLogger(f'{__name__}.get_connection')
	if not hasattr(config, 'connection'):
		con_str = f'DRIVER={{{config.db_driver}}};SERVER={config.db_host};DATABASE={config.db_name};UID={config.db_user};PWD={config.db_pass}'
		log.debug(f'Connection string: {con_str}')
		setattr(config, 'connection', pyodbc.connect(con_str))
		setattr(config, '_finalize', weakref.finalize(config, close_connection, config.connection))
		log.debug(f'config.connection: {config.connection}')
	try:
		# this feels super hacky, but it works...
		with config.connection.cursor() as cursor:
			cursor.execute('SELECT 1')
			result = cursor.fetchone()
			#log.debug(f'config.connection is ok: {config.connection}')
	except:
		log.error(traceback.format_exc())
		log.error(f'config.connection is NOT ok: {config.connection}. Will attempt to re-establish')
		config.connection.close()
		delattr(config, 'connection')
		get_connection(config)
	return config.connection


@TokenList.register('db')
class DBTokenList(TokenList):
	log = logging.getLogger(f'{__name__}.DBTokenList')

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	def load(self, docid: str):
		self.docid = docid
		with get_connection(self.config).cursor() as cursor:
			cursor.execute("""
				SELECT COUNT(*)
				FROM token
				WHERE token.doc_id = ?
				""",
				self.docid,
			)
			result = cursor.fetchone()
			self.tokens = [None] * result[0]

	@property
	def server_ready(self):
		with get_connection(self.config).cursor() as cursor:
			cursor.execute("""
				SELECT COUNT(*)
				FROM token
				WHERE doc_id = ?
				AND decision IS NULL
				""",
				self.docid,
			)
			server_ready = cursor.fetchone()[0] == 0
			DBTokenList.log.debug(f'doc {self.docid} ready for server: {server_ready}')
			return server_ready


	def __getitem__(self, key):
		#DBTokenList.log.debug(f'Getting token at index {key} in {len(self.tokens)} tokens')
		if self.tokens[key] is None:
			self.tokens[key] = DBTokenList._get_token(self.config, self.docid, key)
		return self.tokens[key]

	@staticmethod
	def _get_token(config, docid, index):
		from .. import Token
		with get_connection(config).cursor() as cursor:
			cursor.execute("""
				SELECT *
				FROM token
				LEFT JOIN kbest
				ON token.doc_id = kbest.doc_id AND token.doc_index = kbest.doc_index
				WHERE token.doc_id = ? AND token.doc_index = ?
				ORDER BY kbest.k
				""",
				docid,
				index
			)
			token_dict = None
			for result in cursor:
				# init token with first row
				if not token_dict:
					token_dict = {
						'Token type': result.token_type,
						'Token info': result.token_info,
						'Annotation info': result.annotation_info,
						'Doc ID': result.doc_id,
						'Index': result.doc_index,
						'Gold': result.gold,
						'Bin': result.bin,
						'Heuristic': result.heuristic,
						'Selection': json.loads(result.selection),
						'Decision': result.decision,
						'K': result.k,
						'Hyphenated': result.hyphenated,
						'Discarded': result.discarded,
					}
				# then set k-best from all rows
				token_dict[f"{result.k}-best"] = result.candidate
				token_dict[f"{result.k}-best prob."] = result.probability
			#DBTokenList.log.debug(f'token_dict: {token_dict}')
			if token_dict:
				return Token.from_dict(token_dict)
			else:
				return None

	@staticmethod
	def _save_token(config, token: 'Token'):
		#DBTokenList.log.debug(f'saving token {token.docid}, {token.index}, {token.original}, {token.gold}')
		with get_connection(config).cursor() as cursor:
			cursor.execute("""
				REPLACE INTO token (doc_id, doc_index, original, hyphenated, discarded, gold, bin, heuristic, decision, selection, token_type, token_info, annotation_info) 
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
				""",
				token.docid,
				token.index,
				token.original,
				token.is_hyphenated,
				token.is_discarded,
				token.gold,
				token.bin.number if token.bin else -1,
				token.bin.heuristic if token.bin else '',
				token.decision,
				json.dumps(token.selection),
				token.__class__.__name__,
				json.dumps(token.token_info),
				json.dumps(token.annotation_info),
			)
			if len(token.kbest) > 0:
				kbestdata = []
				for k, item in token.kbest.items():
					kbestdata.append([
					token.docid,
					token.index,
					k,
					item.candidate,
					item.probability,
				])
				cursor.executemany("""
					REPLACE INTO kbest (doc_id, doc_index, k, candidate, probability)
					VALUES (?, ?, ?, ?, ?) 
					""",
					kbestdata,
				)

	@staticmethod
	def _save_all_tokens(config, tokens):
		tokendata = []
		kbestdata = []
		for token in tokens:
			if token is None:
				continue # no need to save tokens that were never loaded.
			tokendata.append([
				token.docid,
				token.index,
				token.original,
				token.is_hyphenated,
				token.is_discarded,
				token.gold,
				token.bin.number if token.bin else -1,
				token.bin.heuristic if token.bin else '',
				token.decision,
				json.dumps(token.selection),
				token.__class__.__name__,
				json.dumps(token.token_info),
				json.dumps(token.annotation_info),
			])
			for k, item in token.kbest.items():
				kbestdata.append([
				token.docid,
				token.index,
				k,
				item.candidate,
				item.probability,
			])
		DBTokenList.log.debug(f'tokendata: {len(tokendata)} kbestdata: {len(kbestdata)}')
		if len(tokendata) == 0:
			DBTokenList.log.debug(f'No tokens to save.')
			return
		with get_connection(config).cursor() as cursor:
			cursor.executemany("""
				REPLACE INTO token (doc_id, doc_index, original, hyphenated, discarded, gold, bin, heuristic, decision, selection, token_type, token_info, annotation_info) 
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
				""",
				tokendata,
			)
			if len(kbestdata) > 0:
				cursor.executemany("""
					REPLACE INTO kbest (doc_id, doc_index, k, candidate, probability)
					VALUES (?, ?, ?, ?, ?) 
					""",
					kbestdata,
				)

	def save(self, token: 'Token' = None):
		DBTokenList.log.info(f'Saving tokens.')
		if token:
			DBTokenList._save_token(self.config, token)
		else:
			DBTokenList._save_all_tokens(self.config, self.tokens)

	@property
	def corrected_count(self):
		with get_connection(self.config).cursor() as cursor:
			cursor.execute("""
				SELECT COUNT(*)
				FROM token
				WHERE token.doc_id = ?
				AND token.gold IS NOT NULL AND token.gold != ''
				""",
				self.docid,
			)
			result = cursor.fetchone()
			return result[0]

	@property
	def discarded_count(self):
		with get_connection(self.config).cursor() as cursor:
			cursor.execute("""
				SELECT COUNT(*)
				FROM token
				WHERE token.doc_id = ?
				AND token.discarded = True
				""",
				self.docid,
			)
			result = cursor.fetchone()
			return result[0]

	def random_token_index(self, has_gold=False, is_discarded=False):
		with get_connection(self.config).cursor() as cursor:
			if has_gold:
				cursor.execute("""
					SELECT MAX(doc_index)
					FROM token
					WHERE token.doc_id = ?
					AND token.discarded = ?
					AND token.gold IS NOT NONE AND token.gold != ''
					""",
					self.docid,
					is_discarded,
				)
			else:
				cursor.execute("""
					SELECT MAX(doc_index)
					FROM token
					WHERE token.doc_id = ?
					AND token.discarded = ?
					""",
					self.docid,
					is_discarded,
				)
			result = cursor.fetchone()
			self.log.debug(f'Result: {result}')
			if len(result) == 0 or result[0] is None:
				return None
			else:
				return random.uniform(0, result[0])

	def random_token(self, has_gold=False, is_discarded=False):
		return self[self.random_token_index(has_gold, is_discarded)]

	@staticmethod
	def exists(config, docid: str):
		DBTokenList.log.debug(f'Checking if tokens for {docid} exist')
		with get_connection(config).cursor() as cursor:
			cursor.execute(
				"SELECT * FROM token WHERE doc_id = ? LIMIT 1",
				docid,
			)
			res = cursor.fetchone()
			DBTokenList.log.debug(f'res: {res}')
			return res is not None

	@staticmethod
	def _get_count(config, docid):
		with get_connection(config).cursor() as cursor:
			cursor.execute(
				"SELECT MAX(doc_index) FROM token WHERE doc_id = ?",
				docid,
			)
			res = cursor.fetchone()[0]
			count = int(res or 0)
			DBTokenList.log.debug(f'_get_count: {count}')
			return count


# for testing:
def logging_execute(cursor, sql, *args) :
	run_sql = sql.replace('?', '{!r}').format(*args)
	try:
		logging.info(run_sql)
		cursor.execute(sql, *args)
	except Exception as e:
		logging.error(f'{run_sql} failed with error {e}')

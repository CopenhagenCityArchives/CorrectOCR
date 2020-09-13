from __future__ import annotations

import abc
import collections
import json
import logging
import weakref

import progressbar
import pyodbc
import random

from ._super import TokenList

def close_connection(connection):
	logging.getLogger(f'{__name__}.close_connection').debug(f'Closing connection {connection}')
	connection.close()

def get_connection(config):
	if not hasattr(config, 'connection'):
		con_str = f'DRIVER={{{config.db_driver}}};SERVER={config.db_host};DATABASE={config.db_name};UID={config.db_user};PWD={config.db_pass}'
		logging.getLogger(f'{__name__}.get_connection').debug(f'Connection string: {con_str}')
		setattr(config, 'connection', pyodbc.connect(con_str))
		setattr(config, '_finalize', weakref.finalize(config, close_connection, config.connection))
		logging.getLogger(f'{__name__}.get_connection').debug(f'config.connection: {config.connection}')
	return config.connection


@TokenList.register('db')
class DBTokenList(TokenList):
	log = logging.getLogger(f'{__name__}.DBTokenList')

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.connection = get_connection(self.config)

	def load(self, docid: str, kind: str):
		self.docid = docid
		self.kind = kind
		
		with self.connection.cursor() as cursor:
			cursor.execute("""
				SELECT COUNT(*)
				FROM token
				WHERE token.doc_id = ? AND token.kind = ?
				""",
				self.docid,
				self.kind
			)
			result = cursor.fetchone()
			self.tokens = [None] * result[0]

	def __getitem__(self, key):
		#DBTokenList.log.debug(f'Getting token at index {key} in {len(self.tokens)} tokens')
		if self.tokens[key] is None:
			self.tokens[key] = DBTokenList._get_token(self.config, self.docid, self.kind, key)
		return self.tokens[key]

	@staticmethod
	def _get_token(config, docid, kind, index):
		from .. import Token
		with get_connection(config).cursor() as cursor:
			cursor.execute("""
				SELECT *
				FROM token
				LEFT JOIN kbest
				ON token.doc_id = kbest.doc_id AND token.doc_index = kbest.doc_index
				WHERE token.doc_id = ? AND token.kind = ? AND token.doc_index = ?
				ORDER BY kbest.k
				""",
				docid,
				kind,
				index
			)
			token_dict = None
			for result in cursor:
				# init token with first row
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
	def _save_token(config, kind, token: 'Token'):
		#DBTokenList.log.debug(f'saving token {token.docid}, {token.index}, {token.original}, {token.gold}')
		with get_connection(config).cursor() as cursor:
			cursor.execute("""
				REPLACE INTO token (kind, doc_id, doc_index, original, hyphenated, discarded, gold, bin, heuristic, decision, selection, token_type, token_info) 
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
				""",
				kind,
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
				json.dumps(token.token_info)
			)
			if len(token.kbest) > 0:
				for k, item in token.kbest.items():
					kbestdata.append([
					token.docid,
					token.index,
					k,
					item.candidate,
					item.probability
				])
				cursor.executemany("""
					REPLACE INTO kbest (doc_id, doc_index, k, candidate, probability)
					VALUES (?, ?, ?, ?, ?) 
					""",
					kbestdata
				)

	@staticmethod
	def _save_all_tokens(config, kind, tokens):
		tokendata = []
		kbestdata = []
		for token in tokens:
			tokendata.append([
				kind,
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
				json.dumps(token.token_info)
			])
			for k, item in token.kbest.items():
				kbestdata.append([
				token.docid,
				token.index,
				k,
				item.candidate,
				item.probability
			])
		DBTokenList.log.debug(f'tokendata: {len(tokendata)} kbestdata: {len(kbestdata)}')
		with get_connection(config).cursor() as cursor:
			cursor.executemany("""
				REPLACE INTO token (kind, doc_id, doc_index, original, hyphenated, discarded, gold, bin, heuristic, decision, selection, token_type, token_info) 
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
				""",
				tokendata
			)
			if len(kbestdata) > 0:
				cursor.executemany("""
					REPLACE INTO kbest (doc_id, doc_index, k, candidate, probability)
					VALUES (?, ?, ?, ?, ?) 
					""",
					kbestdata
				)

	def save(self, kind: str = None, token: 'Token' = None):
		DBTokenList.log.info(f'Saving {kind}')
		if kind:
			self.kind = kind
		if token:
			DBTokenList._save_token(self.config, self.kind, token)
		else:
			DBTokenList._save_all_tokens(self.config, self.kind, self.tokens)

	@property
	def corrected_count(self):
		with self.connection.cursor() as cursor:
			cursor.execute("""
				SELECT COUNT(*)
				FROM token
				WHERE token.doc_id = ? AND token.kind = ?
				AND token.gold IS NOT NULL AND token.gold != ''
				""",
				self.docid,
				self.kind
			)
			result = cursor.fetchone()
			return result[0]

	@property
	def discarded_count(self):
		with self.connection.cursor() as cursor:
			cursor.execute("""
				SELECT COUNT(*)
				FROM token
				WHERE token.doc_id = ? AND token.kind = ?
				AND token.discarded = True
				""",
				self.docid,
				self.kind
			)
			result = cursor.fetchone()
			return result[0]

	def random_token_index(self, has_gold=False, is_discarded=False):
		with self.connection.cursor() as cursor:
			if has_gold:
				cursor.execute("""
					SELECT MAX(doc_index)
					FROM token
					WHERE token.doc_id = ? AND token.kind = ?
					AND token.discarded = ?
					AND token.gold IS NOT NONE AND token.gold != ''
					""",
					self.docid,
					self.kind,
					is_discarded
				)
			else:
				cursor.execute("""
					SELECT MAX(doc_index)
					FROM token
					WHERE token.doc_id = ? AND token.kind = ?
					AND token.discarded = ?
					""",
					self.docid,
					self.kind,
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
	def exists(config, docid: str, kind: str):
		DBTokenList.log.debug(f'Checking if {kind} for {docid} exist')
		with get_connection(config).cursor() as cursor:
			cursor.execute(
				"SELECT * FROM token WHERE doc_id = ? AND kind = ? LIMIT 1",
				docid,
				kind
			)
			res = cursor.fetchone()
			DBTokenList.log.debug(f'res: {res}')
			return res is not None

	@staticmethod
	def _get_count(config, docid):
		with get_connection(config).cursor() as cursor:
			cursor.execute(
				"SELECT MAX(doc_index) FROM token WHERE doc_id = ?",
				docid
			)
			count = int(cursor.fetchone()[0])
			DBTokenList.log.debug(f'_get_count: {count}')
			return count

	@staticmethod
	def all_tokens(config, docid):
		DBTokenList.log.debug(f'Getting all tokens for {docid} (may take a while)')
		all_tokens = collections.defaultdict(list)
		max_index = DBTokenList._get_count(config, docid)
		for kind in 'tokens', 'kbestTokens', 'binnedTokens', 'autocorrectedTokens':
			for index in range(0, max_index):
				t = DBTokenList._get_token(config, docid, kind, index)
				if t:
					all_tokens[kind].append(t)
		return all_tokens


# for testing:
def logging_execute(cursor, sql, *args) :
	run_sql = sql.replace('?', '{!r}').format(*args)
	try:
		logging.info(run_sql)
		cursor.execute(sql, *args)
	except Exception as e:
		logging.error(f'{run_sql} failed with error {e}')

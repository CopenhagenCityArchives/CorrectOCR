from __future__ import annotations

import collections
import json
import logging
import traceback
import weakref

import pyodbc
import progressbar
import random

from ._super import TokenList

def close_connection(connection):
	logging.getLogger(f'{__name__}.close_connection').debug(f'Closing connection {connection}')
	connection.close()

def get_connection(config):
	log = logging.getLogger(f'{__name__}.get_connection')
	con_str = f'DRIVER={{{config.db_driver}}};SERVER={config.db_host};DATABASE={config.db_name};UID={config.db_user};PWD={config.db_pass}'
	#log.debug(f'Connection string: {con_str}')
	connection = pyodbc.connect(con_str)
	#setattr(config, '_finalize', weakref.finalize(config, close_connection, connection))
	return connection


@TokenList.register('db')
class DBTokenList(TokenList):
	log = logging.getLogger(f'{__name__}.DBTokenList')

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	def load(self):
		if self.docid is None:
			raise ValueError('Cannot load a TokenList without a docid!')
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
			DBTokenList.log.debug(f'doc {self.docid} has {len(self.tokens)} tokens')

	def preload(self):
		DBTokenList.log.info(f'Preloading tokens for doc {self.docid}')
		self.tokens = DBTokenList._get_all_tokens(self.config, self.docid, self.tokens)
		DBTokenList.log.debug(f'Preloaded {len(self.tokens)} tokens, first 10: {self.tokens[:10]}')

	@property
	def server_ready(self):
		with get_connection(self.config).cursor() as cursor:
			cursor.execute("""
				SELECT COUNT(*)
				FROM token
				WHERE doc_id = ?
				AND decision IS NULL
				AND discarded != 1
				""",
				self.docid,
			)
			server_ready = cursor.fetchone()[0] == 0
			DBTokenList.log.debug(f'doc {self.docid} ready for server: {server_ready}')
			return server_ready


	def __getitem__(self, key):
		if self.tokens[key] is None:
			#DBTokenList.log.debug(f'Getting token at index {key} in {len(self.tokens)} tokens')
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
				""",
				docid,
				index
			)
			token_dict = None
			for result in cursor:
				#DBTokenList.log.debug(f'result: {result}')
				# pyodbc workaround
				# we must reset the doc_id/doc_index in case there are no kbest
				# because the empty result from the right table (kbest)
				# will overwrite the left table (token)
				# resulting in None when accessed as properties (but not as indexes!)
				result.doc_id = result[0]
				result.doc_index = result[1]
				# init token with first row
				if not token_dict:
					token_dict = {
						'Token type': result.token_type,
						'Token info': result.token_info,
						'Annotations': result.annotations,
						'Has error': result.has_error,
						'Last Modified': result.last_modified,
						'Doc ID': result.doc_id,
						'Index': result.doc_index,
						'Gold': result.gold,
						'Bin': result.bin,
						'Heuristic': result.heuristic,
						'Selection': json.loads(result.selection),
						'Decision': result.decision,
						'Hyphenated': result.hyphenated,
						'Discarded': result.discarded,
						'k-best': dict(),
					}
				# then set k-best from all rows
				if result.k:
					token_dict['k-best'][result.k] = {
						'candidate': result.candidate,
						'probability': result.probability,
					}
			#DBTokenList.log.debug(f'token_dict: {token_dict}')
			if token_dict:
				return Token.from_dict(token_dict)
			else:
				return None

	@staticmethod
	def _get_all_tokens(config, docid, tokens):
		from .. import Token
		with get_connection(config).cursor() as cursor:
			cursor.execute("""
				SELECT *
				FROM token
				LEFT JOIN kbest
				ON token.doc_id = kbest.doc_id AND token.doc_index = kbest.doc_index
				WHERE token.doc_id = ?
				ORDER BY token.doc_id, token.doc_index
				""",
				docid,
			)
			token_dict = None
			for result in progressbar.progressbar(cursor, max_value=cursor.rowcount):
				#DBTokenList.log.debug(f'result: {result}')
				# pyodbc workaround
				# we must reset the doc_id/doc_index in case there are no kbest
				# because the empty result from the right table (kbest)
				# will overwrite the left table (token)
				# resulting in None when accessed as properties (but not as indexes!)
				result.doc_id = result[0]
				result.doc_index = result[1]
				if token_dict and token_dict['Index'] != result.doc_index:
					#DBTokenList.log.debug(f'token_dict: {token_dict}')
					token = Token.from_dict(token_dict)
					tokens[token.index] = token
					token_dict = None
				if not token_dict:
					# init new token
					token_dict = {
						'Token type': result.token_type,
						'Token info': result.token_info,
						'Annotations': result.annotations,
						'Has error': result.has_error,
						'Last Modified': result.last_modified,
						'Doc ID': result.doc_id,
						'Index': result.doc_index,
						'Gold': result.gold,
						'Bin': result.bin,
						'Heuristic': result.heuristic,
						'Selection': json.loads(result.selection),
						'Decision': result.decision,
						'Hyphenated': result.hyphenated,
						'Discarded': result.discarded,
						'k-best': dict(),
					}
				# set k-best from all rows
				if result.k:
					token_dict['k-best'][result.k] = {
						'candidate': result.candidate,
						'probability': result.probability,
					}
			if token_dict:
				# remember the last token!
				token = Token.from_dict(token_dict)
				tokens[token.index] = token
		return tokens

	@staticmethod
	def _save_token(config, token: 'Token'):
		#DBTokenList.log.debug(f'saving token {token.docid}, {token.index}, {token.original}, {token.gold}')
		with get_connection(config).cursor() as cursor:
			cursor.execute("""
				REPLACE INTO token (doc_id, doc_index, original, hyphenated, discarded, gold, bin, heuristic, decision, selection, token_type, token_info, annotations, has_error, last_modified) 
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
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
				json.dumps(token.annotations),
				token.has_error,
				token.last_modified,
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
				json.dumps(token.annotations),
				token.has_error,
				token.last_modified,
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
				REPLACE INTO token (doc_id, doc_index, original, hyphenated, discarded, gold, bin, heuristic, decision, selection, token_type, token_info, annotations, has_error, last_modified) 
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) 
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
		if token:
			DBTokenList.log.info(f'Saving token: {token}.')
			DBTokenList._save_token(self.config, token)
		else:
			DBTokenList.log.info(f'Saving all tokens.')
			DBTokenList._save_all_tokens(self.config, self.tokens)

	@property
	def stats(self):
		stats = collections.defaultdict(int)
		skip_next = False
		with get_connection(self.config).cursor() as cursor:
			cursor.execute("""
				SELECT
					doc_id,
					doc_index,
					discarded,
					hyphenated,
					gold,
					decision,
					has_error
				FROM token
				WHERE token.doc_id = ?
				""",
				self.docid
			)
			for result in cursor.fetchall():
				stats['index_count'] += 1
				if skip_next:
					skip_next = False
					continue
				if result.discarded:
					stats['discarded_count'] += 1
					continue
				stats['token_count'] += 1
				if result.hyphenated:
					stats['hyphenated_count'] += 1
					skip_next = True
				if result.has_error:
					stats['error_count'] += 1
				if result.gold is None:
					stats['uncorrected_count'] += 1
				else:
					stats['corrected_count'] += 1
					if result.decision == 'annotator':
						stats['corrected_by_annotator_count'] += 1
					else:
						stats['corrected_by_model_count'] += 1
					if result.gold == '':
						stats['empty_gold'] += 1
		TokenList.validate_stats(self.docid, stats)
		return stats

	def random_token_index(self, has_gold=False, is_discarded=False):
		with get_connection(self.config).cursor() as cursor:
			if has_gold:
				cursor.execute("""
					SELECT MAX(doc_index)
					FROM token
					WHERE token.doc_id = ?
					AND token.discarded = ?
					AND token.gold IS NOT NULL
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

	@property
	def overview(self):
		with get_connection(self.config).cursor() as cursor:
			cursor.execute("""
				SELECT
					doc_id,
					doc_index,
					original,
					gold,
					discarded,
					decision,
					has_error,
					last_modified
				FROM token
				WHERE token.doc_id = ?
				ORDER BY doc_index
				""",
				self.docid,
			)
			for result in cursor.fetchall():
				yield {
					'doc_id': result.doc_id,
					'doc_index': result.doc_index,
					'string': (result.gold or result.original),
					'is_corrected': (result.gold is not None),
					'is_discarded': bool(result.discarded),
					'has_error': bool(result.has_error),
					'requires_annotator': (result.decision == 'annotator'),
					'last_modified': result.last_modified,
				}

	@property
	def last_modified(self):
		with get_connection(self.config).cursor() as cursor:
			cursor.execute("""
				SELECT
					MAX(last_modified)
				FROM token
				WHERE token.doc_id = ?
				ORDER BY doc_index
				""",
				self.docid,
			)
			res = cursor.fetchone()[0]
			#DBTokenList.log.debug(f'last_modified: {res}')
			return res


# for testing:
def logging_execute(cursor, sql, *args) :
	run_sql = sql.replace('?', '{!r}').format(*args)
	try:
		logging.info(run_sql)
		cursor.execute(sql, *args)
	except Exception as e:
		logging.error(f'{run_sql} failed with error {e}')

from __future__ import annotations

import abc
import collections
import json
import logging
import random
from typing import Tuple

import progressbar

from ..._util import hyphenRE

class TokenList(collections.abc.MutableSequence):
	log = logging.getLogger(f'{__name__}.TokenList')
	_subclasses = dict()

	@staticmethod
	def register(storagetype: str):
		"""
		Decorator which registers a :class:`TokenList` subclass with the base class.

		:param storagetype: `fs` or `db`
		"""
		def wrapper(cls):
			TokenList._subclasses[storagetype] = cls
			return cls
		return wrapper

	@staticmethod
	def new(config, docid = None, tokens = None) -> TokenList:
		if tokens:
			return TokenList.for_type(config.type)(config, docid=docid, tokens=tokens)
		else:
			return TokenList.for_type(config.type)(config, docid=docid)

	@staticmethod
	def for_type(type: str) -> TokenList.__class__:
		TokenList.log.debug(f'_subclasses: {TokenList._subclasses}')
		if type not in TokenList._subclasses:
			raise NameError(f'Unknown storage type: {type}')
		return TokenList._subclasses[type]

	def __init__(self, config, docid = None, tokens = None):
		if type(self) is TokenList:
			raise TypeError('Token base class cannot not be directly instantiated')
		self.config = config
		self.docid = docid
		if tokens:
			self.tokens = tokens
		else:
			self.tokens = list()
		TokenList.log.debug(f'init: {self.config} {self.docid}')

	def __str__(self):
		output = []
		ts = iter(self)
		for t in ts:
			#TokenList.log.debug(f't: {t}')
			output.append(t.gold or t.original)
			#TokenList.log.debug(f'output: {output}')
			if t.is_hyphenated:
				n = next(ts)
				#TokenList.log.debug(f'n: {n}')
				output[-1] = output[-1][:-1] + (n.gold or n.original)
				#TokenList.log.debug(f'output: {output}')
		return str.join(' ', output)

	def __len__(self):
		return len(self.tokens)

	def __delitem__(self, key):
		return self.tokens.__delitem__(key)
	
	def __setitem__(self, key, value):
		return self.tokens.__setitem__(key, value)

	def insert(self, key, value):
		return self.tokens.insert(key, value)

	def __getitem__(self, key):
		return self.tokens.__getitem__(key)

	@abc.abstractmethod
	def load(self):
		pass

	@abc.abstractmethod
	def save(self, token: 'Token' = None):
		pass

	def preload(self):
		pass

	def flush(self):
		pass

	@property
	def stats(self):
		stats = collections.defaultdict(int)
		skip_next = False
		for token in self:
			stats['index_count'] += 1
			if skip_next:
				skip_next = False
				continue
			if token.is_discarded:
				stats['discarded_count'] += 1
				continue
			stats['token_count'] += 1
			if token.is_hyphenated:
				stats['hyphenated_count'] += 1
				skip_next = True
			if token.has_error:
				stats['error_count'] += 1
			if token.gold is None:
				stats['uncorrected_count'] += 1
			else:
				stats['corrected_count'] += 1
				if token.decision == 'annotator':
					stats['corrected_by_annotator_count'] += 1
				else:
					stats['corrected_by_model_count'] += 1
				if token.gold == '':
					stats['empty_gold'] += 1
		TokenList.validate_stats(self.docid, stats)
		return stats

	@classmethod
	def validate_stats(cls, docid, stats):
		for key in ('index_count', 'token_count'):
			if key not in stats:
				cls.log.warn(f'key {key} missing in stats {stats} for doc {docid}')
		if stats['token_count'] + stats['discarded_count'] + stats['hyphenated_count'] != stats['index_count']:
			cls.log.error(f'index counts do not match for stats {stats} for doc {docid}')
		if stats['corrected_by_annotator_count'] + stats['corrected_by_model_count'] != stats['corrected_count']:
			cls.log.error(f'correction counts do not match for stats {stats} for doc {docid}')
		if stats['uncorrected_count'] + stats['corrected_count'] != stats['token_count']:
			cls.log.error(f'correction counts do not match for stats {stats} for doc {docid}')
		if stats['error_count'] > 0:
			cls.log.error(f"there are {stats['error_count']} errors in doc {docid}")
		if stats['token_count'] > 0 and stats['corrected_count'] == stats['token_count'] and stats['error_count'] == 0:
			cls.log.info(f'Marking as done: doc {docid}')
			stats['done'] = True
		else:
			stats['done'] = False

	@property
	def consolidated(self) -> Tuple[str, str, Token]:
		"""
			A consolidated iterator of tokens, where discarded tokens are skipped,
			and hyphenated original/gold are included.
			
			:returns original, gold, token
		"""
		tokens = iter(self)
		for token in tokens:
			if token.is_discarded:
				continue
			original = token.original
			gold = token.gold
			if token.is_hyphenated:
				n = next(tokens)
				original += n.original
				if gold:
					gold += n.gold
			yield original, gold, token

	@property
	def server_ready(self):
		return all(t.decision is not None and not t.is_discarded for t in self.tokens)

	def random_token_index(self, has_gold=False, is_discarded=False):
		return self.random_token(has_gold, is_discarded).index

	def random_token(self, has_gold=False, is_discarded=False):
		filtered_tokens = filter(lambda t: t.is_discarded == is_discarded, self.tokens)
		if has_gold:
			filtered_tokens = filter(lambda t: t.gold and t.gold != '', filtered_tokens)
		filtered_tokens = list(filtered_tokens)
		if len(filtered_tokens) == 0:
			return None
		else:
			return random.choice(filtered_tokens)

	@property
	def overview(self):
		"""
			Generator that returns an fast overview of the TokenList.
			
			Each item is a dictionary containing the following keys:
			
			  - ``doc_id``: The document
			  - ``doc_index``: The Token's placement in the document
			  - ``string``: TODO
			  - ``is_corrected``: Whether the Token has a set gold property
			  - ``is_discarded``: Whether the Token is marked as discarded
		"""
		for token in self.tokens:
			yield {
				'doc_id': token.docid,
				'doc_index': token.index,
				'string': (token.gold or token.original),
				'is_corrected': (token.gold is not None),
				'is_discarded': token.is_discarded,
				'has_error': token.has_error,
				'requires_annotator': (token.decision == 'annotator'),
				'last_modified': token.last_modified,
			}

	@property
	def user_stats(self):
		user_stats = collections.Counter()
		for token in self.tokens:
			user_stats[json.dumps(token.annotation_info)] += 1 # kind of hacky...
		return user_stats

	@property
	def last_modified(self):
		return max(t.last_modified for t in self.tokens if t.last_modified)

	def dehyphenate(self):
		TokenList.log.debug(f'Going to dehyphenate {len(self.tokens)} tokens')
		count = 0
		tokens = iter(self)
		for token in progressbar.progressbar(tokens, max_value=len(self.tokens)):
			if hyphenRE.search(token.original):
				try:
					token.is_hyphenated = True
					next(tokens).gold = ''
					count += 1
				except StopIteration:
					TokenList.log.warning(f'Final token appears to end in a hyphen. Will ignore! {token}')
		TokenList.log.debug(f'Dehyphenated {count} tokens')


##########################################################################################



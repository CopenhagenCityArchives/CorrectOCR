from __future__ import annotations

import abc
import collections
import logging
import random


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

	@staticmethod
	def exists(config, docid: str) -> bool:
		return TokenList.for_type(config.type).exists(config, docid)

	@abc.abstractmethod
	def load(self, docid: str):
		pass

	@abc.abstractmethod
	def save(self, token: 'Token' = None):
		pass

	@property
	def corrected_count(self):
		return len([t for t in self if t.gold and t.gold != ''])

	@property
	def discarded_count(self):
		return len([t for t in self if not t.is_discarded])

	@property
	def server_ready(self):
		return all(t.decision is not None for t in self.tokens)

	def save(self, token: 'Token' = None):
		pass
	
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
				'is_corrected': (token.gold is not None and token.gold.strip() != ''),
				'is_discarded': token.is_discarded,
				'last_modified': token.last_modified,
			}

	@property
	def last_modified(self):
		return max(t.last_modified for t in self.tokens)

##########################################################################################



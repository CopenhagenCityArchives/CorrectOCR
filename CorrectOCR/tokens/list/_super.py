from __future__ import annotations

import abc
import collections
import logging
from typing import List


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
	def new(config, tokens = None) -> TokenList:
		if tokens:
			return TokenList.for_type(config.type)(config, tokens)
		else:
			return TokenList.for_type(config.type)(config)

	@staticmethod
	def for_type(type: str) -> TokenList.__class__:
		TokenList.log.debug(f'_subclasses: {TokenList._subclasses}')
		if type not in TokenList._subclasses:
			raise NameError(f'Unknown storage type: {type}')
		return TokenList._subclasses[type]

	def __init__(self, config, *args):
		self.config = config
		self.docid = None
		self.kind = None
		self.tokens = []
		TokenList.log.debug(f'init: {self.config}')

	def __len__(self):
		return len(self.tokens)

	def __delitem__(self, key):
		return self.tokens.__delitem__(key)
	
	def __setitem__(self, key, value):
		return self.tokens.__setitem__(key, value)

	def __str__(self):
		#TokenList.log.debug(f'tokens: {self.tokens}') 
		output = ''
		ts = iter(self)
		for t in ts:
			#TokenList.log.debug(f't: {t}')
			output += t.gold or t.original
			#TokenList.log.debug(f'output: {output}')
			if t.is_hyphenated:
				n = next(ts)
				#TokenList.log.debug(f'n: {n}')
				output = output[:-1] + (n.gold or n.original)
				#TokenList.log.debug(f'output: {output}')
		return output

	def insert(self, key, value):
		return self.tokens.insert(key, value)

	@staticmethod
	def exists(config, docid: str, kind: str) -> bool:
		return TokenList.for_type(config.type).exists(config, docid, kind)

	@abc.abstractmethod
	def load(self, docid: str, kind: str):
		pass

	@abc.abstractmethod
	def save(self, kind: str = None, token: 'Token' = None):
		pass

	@abc.abstractmethod
	def corrected_count(self):
		pass

##########################################################################################



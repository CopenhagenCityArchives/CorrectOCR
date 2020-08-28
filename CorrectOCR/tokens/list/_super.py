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
	def new(config, docid = None, kind = None, tokens = None) -> TokenList:
		if tokens:
			return TokenList.for_type(config.type)(config, docid=docid, kind=kind, tokens=tokens)
		else:
			return TokenList.for_type(config.type)(config, docid=docid, kind=kind)

	@staticmethod
	def for_type(type: str) -> TokenList.__class__:
		TokenList.log.debug(f'_subclasses: {TokenList._subclasses}')
		if type not in TokenList._subclasses:
			raise NameError(f'Unknown storage type: {type}')
		return TokenList._subclasses[type]

	def __init__(self, config, docid = None, kind = None, tokens = list()):
		if type(self) is TokenList:
			raise TypeError("Token base class cannot not be directly instantiated")
		self.config = config
		self.docid = docid
		self.kind = kind
		self.tokens = tokens
		TokenList.log.debug(f'init: {self.config} {self.docid} {self.kind}')

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
	def exists(config, docid: str, kind: str) -> bool:
		return TokenList.for_type(config.type).exists(config, docid, kind)

	@abc.abstractmethod
	def load(self, docid: str, kind: str):
		pass

	@abc.abstractmethod
	def save(self, kind: str = None, token: 'Token' = None):
		pass

	@property
	@abc.abstractmethod
	def corrected_count(self):
		pass

##########################################################################################



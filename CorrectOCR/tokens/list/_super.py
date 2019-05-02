from __future__ import annotations

import abc
import logging
from typing import List


class TokenList(List['Token'], abc.ABC):
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
		list.__init__(self, *args)
		self.config = config
		TokenList.log.debug(f'init: {self.config}')

	@staticmethod
	def exists(config, path) -> bool:
		return TokenList.new(config)._exists(path) #TODO

	@abc.abstractmethod
	def load(self, fileid: str, path = None):
		pass

	@abc.abstractmethod
	def save(self, path = None, token = None):
		pass

	@staticmethod
	@abc.abstractmethod
	def _exists(self, path):
		pass

##########################################################################################



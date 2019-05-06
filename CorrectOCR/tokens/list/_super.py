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

		:param type: TODO
		"""
		def wrapper(cls):
			TokenList._subclasses[storagetype] = cls
			return cls
		return wrapper

	@staticmethod
	def for_type(type: str) -> 'TokenList':
		TokenList.log.debug(f'_subclasses: {TokenList._subclasses}')
		if type not in TokenList._subclasses:
			raise Error('Unknown storage type: {type}')
		return TokenList._subclasses[type]

	def __init__(self, config, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.config = config
		TokenList.log.debug(f'init: {self.config}')

	@classmethod
	@abc.abstractmethod
	def load(cls, fileid: str, name: str) -> 'TokenList':
		pass

	@abc.abstractmethod
	def save(self):
		pass

    @classmethod
    @abc.abstractmethod
    def load(cls, fileid: str) -> 'TokenList':
        pass

    @abc.abstractmethod
    def save(self, name: str):
        pass


##########################################################################################

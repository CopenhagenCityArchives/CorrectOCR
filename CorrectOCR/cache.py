import logging
import weakref
from pathlib import Path

from cachetools import LRUCache, cachedmethod

from .fileio import FileIO


class PickledLRUCache(LRUCache):
	log = logging.getLogger(f'{__name__}.PickledLRUCache')
	size = 1024*10

	@classmethod
	def by_name(cls, name):
		path = Path('./__COCRcache__/').joinpath(f'{name}.pickle')
		if path.is_file():
			cache = FileIO.load(path)
			PickledLRUCache.log.info(f'Loaded {path}: {cache.currsize} items.')
			#PickledLRUCache.log.debug(f'{repr(cache)}')
			cache._finalize = weakref.finalize(cache, PickledLRUCache.save, cache)
			return cache
		else:
			return cls(path, maxsize=PickledLRUCache.size)

	def __init__(self, path, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.path = path
		self._finalize = weakref.finalize(self, PickledLRUCache.save, self)

	def save(self):
		PickledLRUCache.log.info(f'Saving {self.currsize} items to {self.path}')
		FileIO.save(self, self.path, backup=False)

	def delete(self):
		FileIO.delete(self.path)

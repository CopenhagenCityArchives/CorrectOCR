import logging
from typing import List, Iterator

from .workspace import Workspace


class Dictionary(object):
	log = logging.getLogger(f'{__name__}.Dictionary')

	@property
	def data(self) -> List[str]:
		return sorted(self.words, key=str.lower)
	
	def __init__(self, path=None, caseInsensitive=False):
		self.caseInsensitive = caseInsensitive
		self.words = set()
		self.path = path
		if self.path.exists():
			Dictionary.log.info(f'Loading dictionary from {self.path.name}')
			for line in Workspace.load(self.path).split('\n'):
				if self.caseInsensitive:
					self.words.add(line.strip().lower())
				else:
					self.words.add(line.strip())
		Dictionary.log.info(f'{len(self.words)} words in dictionary')
	
	def __str__(self) -> str:
		return f'<{self.__class__.__name__} "{len(self.words)}{" caseInsensitive" if self.caseInsensitive else ""}>'
	
	def __repr__(self) -> str:
		return self.__str__()
	
	def __contains__(self, word: str) -> bool:
		"""Contains all numbers"""
		if word.isnumeric():
			return True
		if self.caseInsensitive:
			word = word.lower()
		return word in self.words
	
	def __iter__(self) -> Iterator[str]:
		return self.words.__iter__()
	
	def __len__(self) -> int:
		return self.words.__len__()
	
	def add(self, word: str):
		"""Silently drops non-alpha strings"""
		if word in self or not word.isalpha():
			return
		if len(word) > 15:
			Dictionary.log.warning(f'Added word is more than 15 characters long: {word}')
		if self.caseInsensitive:
			word = word.lower()
		self.words.add(word)
	
	def save(self, path=None):
		path = path or self.path
		Dictionary.log.info(f'Saving dictionary (words: {len(self.words)}) to {path}')
		Workspace.save('\n'.join(self.data), path)

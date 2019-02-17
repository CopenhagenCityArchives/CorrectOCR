import logging
from typing import List, Set

from .workspace import Workspace


class Dictionary(Set[str]):
	log = logging.getLogger(f'{__name__}.Dictionary')

	@property
	def data(self) -> List[str]:
		return sorted(self, key=str.lower)
	
	def __init__(self, path=None, caseInsensitive=False):
		super().__init__()
		self.caseInsensitive = caseInsensitive
		self.path = path
		if self.path and self.path.is_file():
			Dictionary.log.info(f'Loading dictionary from {self.path.name}')
			for line in Workspace.load(self.path).split('\n'):
				if self.caseInsensitive:
					self.add(line.strip().lower(), nowarn=True)
				else:
					self.add(line.strip(), nowarn=True)
		Dictionary.log.info(f'{len(self)} words in dictionary')
	
	def __str__(self) -> str:
		return f'<{self.__class__.__name__} "{len(self)}{" caseInsensitive" if self.caseInsensitive else ""}>'
	
	def __repr__(self) -> str:
		return self.__str__()
	
	def __contains__(self, word: str) -> bool:
		"""Contains all numbers"""
		if word.isnumeric():
			return True
		if self.caseInsensitive:
			word = word.lower()
		return super().__contains__(word)
	
	def add(self, word: str, nowarn=False):
		"""Silently drops non-alpha strings"""
		if not word.isalpha() or word in self:
			return
		if len(word) > 15 and not nowarn:
			Dictionary.log.warning(f'Added word is more than 15 characters long: {word}')
		if self.caseInsensitive:
			word = word.lower()
		return super().add(word)
	
	def save(self, path=None):
		path = path or self.path
		Dictionary.log.info(f'Saving dictionary (words: {len(self)}) to {path}')
		Workspace.save('\n'.join(self.data), path)

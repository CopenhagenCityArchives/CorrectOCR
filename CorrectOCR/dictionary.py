import logging
from pathlib import Path
from typing import Set

from .fileio import FileIO


class Dictionary(Set[str]):
	"""
	Set of words to use for determining correctness of :class:`Tokens<CorrectOCR.tokens.Token>` and suggestions.
	"""
	log = logging.getLogger(f'{__name__}.Dictionary')

	def __init__(self, path: Path = None, caseInsensitive: bool = False):
		"""
		:param path: A path for loading a previously saved dictionary.
		:param caseInsensitive: Whether the dictionary is case sensitive.
		"""
		super().__init__()
		self.caseInsensitive = caseInsensitive
		self._path = path
		if self._path and self._path.is_file():
			Dictionary.log.info(f'Loading dictionary from {self._path.name}')
			for line in FileIO.load(self._path).split('\n'):
				if self.caseInsensitive:
					self.add(line.lower(), nowarn=True)
				else:
					self.add(line, nowarn=True)
		Dictionary.log.info(f'{len(self)} words in dictionary')
	
	def __repr__(self) -> str:
		return f'<{self.__class__.__name__} "{len(self)}{" caseInsensitive" if self.caseInsensitive else ""}>'
	
	def __contains__(self, word: str) -> bool:
		if word.isnumeric():
			return True
		if self.caseInsensitive:
			word = word.lower()
		return super().__contains__(word)

	def clear(self):
		Dictionary.log.info(f'Clearing dictionary at {self._path}.')
		FileIO.ensure_new_file(self._path)
		super().clear()

	def add(self, word: str, nowarn: bool = False):
		"""
		Add a new word to the dictionary. Silently drops non-alpha strings.

		:param word: The word to add.
		:param nowarn: Don't warn about long words (>15 letters).
		"""
		word = word.strip()
		if word == '' or not word.isalpha() or word in self:
			return
		if len(word) > 15 and not nowarn:
			Dictionary.log.warning(f'Added word is more than 15 characters long: {word}')
		if self.caseInsensitive:
			word = word.lower()
		return super().add(word)
	
	def save(self, path: Path = None):
		"""
		Save the dictionary.

		:param path: Optional new path to save to.
		"""
		path = path or self._path
		Dictionary.log.info(f'Saving dictionary (words: {len(self)}) to {path}')
		FileIO.save('\n'.join(sorted(self, key=str.lower)), path)

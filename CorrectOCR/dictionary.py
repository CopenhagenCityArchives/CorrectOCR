import logging
from pathlib import Path
from typing import Set

from ._util import punctuationRE
from .fileio import FileIO

class Dictionary(Set[str]):
	"""
	Set of words to use for determining correctness of :class:`Tokens<CorrectOCR.tokens.Token>` and suggestions.
	"""
	log = logging.getLogger(f'{__name__}.Dictionary')

	def __init__(self, path: Path = None, ignoreCase: bool = False):
		"""
		:param path: A path for loading a previously saved dictionary.
		:param ignoreCase: Whether the dictionary is case sensitive.
		"""
		super().__init__()
		self.ignoreCase = ignoreCase
		self._path = path
		if self._path and self._path.is_file():
			Dictionary.log.info(f'Loading dictionary from {self._path.name}')
			for line in FileIO.load(self._path).split('\n'):
				self.add(line, nowarn=True)
		Dictionary.log.info(f'{len(self)} words in dictionary')
	
	def __repr__(self) -> str:
		return f'<{self.__class__.__name__} "{len(self)}{" ignoreCase" if self.ignoreCase else ""}>'
	
	def __contains__(self, word: str) -> bool:
		if word.isnumeric():
			return True
		if self.ignoreCase:
			word = word.lower()
		return super().__contains__(word)

	def clear(self):
		Dictionary.log.info(f'Clearing dictionary at {self._path}.')
		FileIO.ensure_new_file(self._path)
		super().clear()

	def add(self, word: str, nowarn: bool = False):
		"""
		Add a new word (sans punctuation) to the dictionary. Silently drops non-alpha strings.

		:param word: The word to add.
		:param nowarn: Don't warn about long words (>15 letters).
		"""
		word = punctuationRE.sub('', word).strip()
		if word == '' or not word.isalpha() or word in self:
			return
		if len(word) > 15 and not nowarn:
			Dictionary.log.warning(f'Added word is more than 15 characters long: {word}')
		if self.ignoreCase:
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

import logging
import itertools
import string
from collections import defaultdict
from pathlib import Path
from typing import Set

import progressbar

from ._util import letterRE
from .fileio import FileIO


class Dictionary(Set[str]):
	"""
	Set of words to use for determining correctness of :class:`Tokens<CorrectOCR.tokens.Token>` and suggestions.
	
	**Note**: A Dictionary "contains" all "words" that do not contain alphabetic letters, such as ``8,5`` or ``(600)``.
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
		self.groups = defaultdict(set)
		self._dirty = set()
		if self._path:
			if not self._path.is_dir():
				FileIO.ensure_directories(self._path)
			else:
				Dictionary.log.info(f'Loading dictionary from {self._path}')
				for file in progressbar.progressbar(self._path.iterdir()):
					for line in FileIO.load(file).split('\n'):
						self.add(file.stem, line, nowarn=True, dirty=False)
		Dictionary.log.info(f'{len(self)} words in dictionary')
	
	def __repr__(self) -> str:
		return f'<{self.__class__.__name__} "{len(self)}{" ignoreCase" if self.ignoreCase else ""}>'

	def __len__(self) -> int:
		return len(set().union(*self.groups.values()))
		#return len([len(group) for group in self.groups.values()])

	def __contains__(self, word: str) -> bool:
		word = self.clean(word)
		if word == '' or not letterRE.search(word):
			return True
		if self.ignoreCase:
			word = word.lower()
		for group in self.groups.values():
			if word in group:
				return True
		return False

	def has_group(self, group: str) -> bool:
		return group in self.groups

	def clear(self):
		Dictionary.log.info(f'Clearing dictionary at {self._path}.')
		FileIO.ensure_new_file(self._path) # TODO
		self.groups = defaultdict(set)

	def add(self, group: str, word: str, nowarn: bool = False, dirty: bool = True):
		"""
		Add a new word (sans punctuation) to the dictionary. Silently drops non-alpha strings.

		:param word: The word to add.
		:param nowarn: Don't warn about long words (>20 letters).
		"""
		word = self.clean(word)
		if word == '' or not letterRE.search(word):
			return
		if ' ' in word:
			Dictionary.log.info(f'Splitting word with spaces: {word}')
			for w in word.split(' '):
				if w not in self:
					self.add(group, w, nowarn, dirty)
			return
		if self.ignoreCase:
			word = word.lower()
		if dirty and word not in self.groups[group]:
			self._dirty.add(group)
		if len(word) > 20 and not nowarn:
			Dictionary.log.warning(f'Added word is more than 20 characters long: {word}')
		return self.groups[group].add(word)
	
	def save_group(self, group: str):
		path = self._path.joinpath(group)
		if len(self.groups[group]) == 0:
			FileIO.delete(path)
		else:
			Dictionary.log.info(f'Saving group (words: {len(self.groups[group])}) to {path}')
			FileIO.save('\n'.join(sorted(self.groups[group], key=str.lower)), path, backup=False)
	
	def save(self, path: Path = None):
		"""
		Save the dictionary.

		:param path: Optional new path to save to.
		"""
		if path:
			self._path = path
		Dictionary.log.info(f'Saving dictionary (total words: {len(self)})')
		#Dictionary.log.debug(f'Dirty groups: {self._dirty}')
		for group in self.groups.keys():
			if group in self._dirty:
				self.save_group(group)

	def clean(self, word: str) -> str:
		word = word.replace('\xad', '') # remove soft hyphens
		word = word.replace('-', '') # remove hard hyphens
		word = word.strip(string.punctuation + string.whitespace + '»«“”„›‹') # strip surrounding punctuation and quotation marks
		return word

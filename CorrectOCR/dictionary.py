import logging
from pathlib import Path

from . import open_for_reading, ensure_new_file, extract_text_from_pdf


class Dictionary(object):
	def __init__(self, path=None, caseInsensitive=False):
		self.log = logging.getLogger(f'{__name__}.Dictionary')
		self.caseInsensitive = caseInsensitive
		self.words = set()
		self.path = path
		if self.path.exists():
			self.log.info(f'Loading dictionary from {self.path.name}')
			with open_for_reading(self.path) as f:
				for line in f.readlines():
					if self.caseInsensitive:
						self.words.add(line.strip().lower())
					else:
						self.words.add(line.strip())
		self.log.info(f'{len(self.words)} words in dictionary')
	
	def __str__(self):
		return f'<{self.__class__.__name__} "{len(self.words)}{" caseInsensitive" if self._optional else ""}>'
	
	def __repr__(self):
		return self.__str__()
	
	def __contains__(self, word):
		"""Contains all numbers"""
		if word.isnumeric():
			return True
		if self.caseInsensitive:
			word = word.lower()
		return word in self.words
	
	def __iter__(self):
		return self.words.__iter__()
	
	def __len__(self):
		return self.words.__len__()
	
	def add(self, word):
		"""Silently drops non-alpha strings"""
		if word in self or not word.isalpha():
			return
		if len(word) > 15:
			self.log.warn(f'Added word is more than 15 characters long: {word}')
		if self.caseInsensitive:
			word = word.lower()
		self.words.add(word)
	
	def save(self, path=None):
		path = path or self.path
		backup = ensure_new_file(path)
		self.log.info(f'Backed up original dictionary file to {backup}')
		self.log.info(f'Saving dictionary (words: {len(self.words)}) to {path}')
		with open(path, 'w', encoding='utf-8') as f:
			for word in sorted(self.words, key=str.lower):
				f.write(f'{word}\n')

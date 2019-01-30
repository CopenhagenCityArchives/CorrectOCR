import logging
import random
import shutil
import time
from pathlib import Path

import requests

from . import open_for_reading, ensure_new_file, extract_text_from_pdf


class Dictionary(object):
	def __init__(self, file, caseInsensitive=False):
		self.caseInsensitive = caseInsensitive
		self.words = set()
		self.file = file
		self.log = logging.getLogger(f'{__name__}.Dictionary')
		if Path(self.file.name).exists():
			self.log.info(f'Loading dictionary from {self.file.name}')
			for line in self.file.readlines():
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
	
	def save(self):
		self.file.close()
		name = self.file.name
		newname = ensure_new_file(Path(self.file.name))
		self.log.info(f'Backed up original dictionary file to {newname}')
		self.log.info(f'Saving dictionary (words: {len(self.words)}) to {name}')
		with open(name, 'w', encoding='utf-8') as f:
			for word in sorted(self.words, key=str.lower):
				f.write(f'{word}\n')


def build_dictionary(config):
	newdict = Dictionary(config.dictionaryFile)
	
	log = logging.getLogger(f'{__name__}.build_dictionary')
	
	from .tokenizer import tokenize_string
	
	if config.corpusFile:
		for line in config.corpusFile.readlines():
			line = line.strip()
			if len(line) == 0:
				pass
			elif line[0] == '#':
				log.info(line)
			elif line[:4] == 'http':
				outfile = config.corpusPath.joinpath(Path(line).name)
				if outfile.exists():
					log.info('Download cached, will not download again.')
					continue
				r = requests.get(line)
				if r.status_code == 200:
					with open(outfile, 'wb') as f:
						f.write(r.content)
				else:
					log.error(f'Unable to save file: {r}')
				time.sleep(random.uniform(0.5, 1.5))
			elif line[-1] == '/':
				for file in Path(line).iterdir():
					outfile = config.corpusPath.joinpath(Path(line).name)
					if outfile.exists():
						log.info(f'File already copied: {file}')
						continue
					log.info(f'Copying {file} to corpus.')
					shutil.copy(file, outfile)
	
	for file in config.corpusPath.iterdir():
		log.info(f'Getting words from {file}')
		if file.suffix == '.pdf':
			text = extract_text_from_pdf(file)
			for word in tokenize_string(str(text), objectify=False):
				newdict.add(word)
		elif file.suffix == '.txt':
			with open_for_reading(file) as f:
				for word in tokenize_string(f.read(), objectify=False):
					newdict.add(word)
		else:
			log.error(f'Unrecognized filetype:{file}')
		log.info(f'Wordcount {len(newdict)}')
	
	newdict.save()

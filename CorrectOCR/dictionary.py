#!/usr/bin/env python

import shutil
import random
import time
import logging
from pathlib import Path

import requests

from . import open_for_reading, ensure_new_file


class Dictionary(object):
	def __init__(self, file, caseInsensitive=False):
		self.caseInsensitive = caseInsensitive
		self.words = set()
		self.file = file
		self.log = logging.getLogger(__name__+'.Dictionary')
		if Path(self.file.name).exists():
			self.log.info('Loading dictionary from {}'.format(self.file.name))
			for line in self.file.readlines():
				if self.caseInsensitive:
					self.words.add(line.strip().lower())
				else:
					self.words.add(line.strip())
		self.log.info('{} words in dictionary'.format(len(self.words)))
	
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
			self.log.warn('Added word is more than 15 characters long: {}'.format(word))
		if self.caseInsensitive:
			word = word.lower()
		self.words.add(word)
	
	def save(self):
		self.file.close()
		name = self.file.name
		newname = ensure_new_file(Path(self.file.name))
		self.log.info('Backed up original dictionary file to {}'.format(newname))
		self.log.info('Saving dictionary (words: {}) to {}'.format(len(self.words), name))
		with open(name, 'w', encoding='utf-8') as f:
			for word in sorted(self.words, key=str.lower):
				f.write(word + '\n')


def extract_text_from_pdf(filename):
	import fitz
	
	doc = fitz.open(filename)
	
	text = ''
	
	for p in range(0, doc.pageCount):
		page = doc.loadPage(p)
		
		text += page.getText()
	
	return text


def build_dictionary(config):
	newdict = Dictionary(config.dictionaryFile)
	
	log = logging.getLogger(__name__+'.build_dictionary')
	
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
					log.error('Unable to save file: {}'.format(r))
				time.sleep(random.uniform(0.5, 1.5))
			elif line[-1] == '/':
				for file in Path(line).iterdir():
					outfile = config.corpusPath.joinpath(Path(line).name)
					if outfile.exists():
						log.info('File already copied: {}'.format(file))
						continue
					log.info('Copying {} to corpus.'.format(file))
					shutil.copy(file, outfile)
	
	for file in config.corpusPath.iterdir():
		log.info('Getting words from {}'.format(file))
		if file.suffix == '.pdf':
			text = extract_text_from_pdf(file)
			for word in tokenize_string(str(text), objectify=False):
				newdict.add(word)
		elif file.suffix == '.txt':
			with open_for_reading(file) as f:
				for word in tokenize_string(f.read(), objectify=False):
					newdict.add(word)
		else:
			log.error('Unrecognized filetype:{}'.format(file))
		log.info('Wordcount {}'.format(len(newdict)))
	
	newdict.save()

#!/usr/bin/env python

import re
import textract
import logging
from pathlib import Path

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
		if word.isnumeric():
			return
		if self.caseInsensitive:
			word = word.lower()
		self.words.add(word)
	
	def save(self):
		name = self.file.name
		newname = ensure_new_file(Path(self.file.name))
		self.log.info('Backed up original dictionary file to {}'.format(newname))
		self.log.info('Saving dictionary (words: {}) to {}'.format(len(self.words), name))
		with open(name, 'w', encoding='utf-8') as f:
			for word in sorted(self.words, key=str.lower):
				f.write(word + '\n')


def extract_text_from_pdf(pdf_path):
	# see https://www.blog.pythonlibrary.org/2018/05/03/exporting-data-from-pdfs-with-python/
	import io
	from pdfminer.converter import TextConverter
	from pdfminer.pdfinterp import PDFPageInterpreter
	from pdfminer.pdfinterp import PDFResourceManager
	from pdfminer.pdfpage import PDFPage
	from pdfminer.layout import LAParams
	
	# pdfminer sprays a ton of debug/info output
	logging.getLogger('pdfminer').setLevel(logging.WARNING)
	
	resource_manager = PDFResourceManager()
	fake_file_handle = io.StringIO()
	laparams = LAParams()
	converter = TextConverter(resource_manager, fake_file_handle, laparams=laparams)
	page_interpreter = PDFPageInterpreter(resource_manager, converter)
	
	with open(pdf_path, 'rb') as fh:
		for page in PDFPage.get_pages(fh,
                                caching=True,
                                check_extractable=True):
			page_interpreter.process_page(page)
		
		text = fake_file_handle.getvalue()
	
	# close open handles
	converter.close()
	fake_file_handle.close()
	
	if text:
		return text


def build_dictionary(settings):
	charset = re.sub(r'\W+', r'', settings.characterSet)
	
	newdict = Dictionary(settings.dictionaryFile)
	
	for file in settings.files:
		logging.getLogger(__name__).info('Getting words from {}'.format(file))
		if file.suffix == '.pdf':
			text = extract_text_from_pdf(file)
			for word in re.findall(r'\w+', str(text), re.IGNORECASE):
				newdict.add(word)
		elif file.suffix == '.txt':
			with open_for_reading(file) as f:
				for word in re.findall(r'\w+', f.read(), re.IGNORECASE):
					newdict.add(word)
		else:
			logging.getLogger(__name__).error('Unrecognized filetype:{}'.format(file))
		logging.getLogger(__name__).info('Wordcount {}'.format(len(newdict)))
	
	newdict.save()

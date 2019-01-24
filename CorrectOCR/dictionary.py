#!/usr/bin/env python

import datrie
import re
import textract
import logging
from pathlib import Path

from . import open_for_reading


class Dictionary(object):
	def __init__(self, file, caseInsensitive=False):
		self.caseInsensitive = caseInsensitive
		self.words = set()
		self.path = file
		self.log = logging.getLogger(__name__+'.Dictionary')
		self.log.info('Loading dictionary from ' + self.path)
		with open_for_reading(self.path) as f:
			for line in f.readlines():
				if self.caseInsensitive:
					self.words.add(line.strip().lower())
				else:
					self.words.add(line.strip())
	
	def __contains__(self, word):
		if self.caseInsensitive:
			word = word.lower()
		return word in self.words
	
	def add(self, word):
		if self.caseInsensitive:
			word = word.lower()
		self.words.add(word)
	
	def save(self):
		with open(self.path, 'w', encoding='utf-8') as f:
			f.writelines(sorted(self.words, key=str.lower))
	
	def set(self):
		return self.words


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
	(charset, output, files) = (re.sub(r'\W+', r'', settings.characterSet), settings.output, settings.files) # TODO option to add to existing dictionary?
	words = datrie.BaseTrie(charset)
	
	for file in files:
		logging.getLogger(__name__).info('Getting words from '+file)
		if Path(file).suffix == '.pdf':
			text = extract_text_from_pdf(file)
			for word in re.findall(r'\w+', str(text), re.IGNORECASE):
				words[word] = 1
		elif Path(file).suffix == '.txt':
			with open_for_reading(file) as f:
				for word in re.findall(r'\w+', f.read(), re.IGNORECASE):
					words[word] = 1
		else:
			logging.getLogger(__name__).error('Unrecognized filetype: %s' % file)
	
	for word in sorted(words.keys(), key=str.lower):
		output.write(word + '\n')
	output.close()

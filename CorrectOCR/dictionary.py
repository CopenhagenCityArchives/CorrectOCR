#!/usr/bin/env python

import datrie
import re
import textract
import os

def extract_text_from_pdf(pdf_path):
	# see https://www.blog.pythonlibrary.org/2018/05/03/exporting-data-from-pdfs-with-python/
	import io
	from pdfminer.converter import TextConverter
	from pdfminer.pdfinterp import PDFPageInterpreter
	from pdfminer.pdfinterp import PDFResourceManager
	from pdfminer.pdfpage import PDFPage
	from pdfminer.layout import LAParams
	
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


def build_dictionary(config, output, files): # TODO option to add to existing dictionary?
	words = datrie.BaseTrie('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÆØÅæøåäëïöü') # TODO use filtered additionalCharacters?
	
	for file in files:
		print(file)
		if os.path.splitext(file)[1] == '.pdf':
			text = extract_text_from_pdf(file)
			print(text)
			for word in re.findall(r'\w+', str(text), re.IGNORECASE):
				print(word)
				words[word] = 1
		elif os.path.splitext(file)[1] == '.txt':
			with open(file, encoding='utf-8') as f:
				for word in re.findall(r'\w+', f.read(), re.IGNORECASE):
					words[word] = 1
		else:
			print('unrecognized filetype: %s' % file)
	
	for word in sorted(words.keys()):
		output.write(word + '\n')
	output.close()

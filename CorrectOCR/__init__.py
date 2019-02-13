#!/usr/bin/env python

import json
import logging
from collections import deque
from pathlib import Path

import regex
from bs4 import UnicodeDammit


punctuationRE = regex.compile(r'\p{punct}+')


def get_encoding(file):
	with open(file, 'rb') as f:
		dammit = UnicodeDammit(f.read(1024*500), ['utf-8', 'Windows-1252'])
		logging.getLogger(f'{__name__}.get_encoding').debug(f'detected {dammit.original_encoding} for {file}')
		return dammit.original_encoding


def open_for_reading(file):
	return open(file, 'r', encoding=get_encoding(file))


def splitwindow(l, before=3, after=3):
	a = deque(maxlen=before)
	for i in range(len(l)):
		yield list(a), l[i], l[i+1:i+1+after]
		a.append(l[i])


def ensure_new_file(path):
	counter = 0
	originalpath = path
	while Path(path).is_file():
		path = Path(
			path.parent,
			f'{originalpath.stem}.{counter:03n}{originalpath.suffix}'
		)
		counter += 1
	if counter > 0:
		logging.getLogger(f'{__name__}.ensure_new_file').info(f'Existing file moved to {path}')
		originalpath.rename(path)
	return path


def extract_text_from_pdf(filename):
	import fitz
	
	doc = fitz.open(filename)
	
	text = ''
	
	for p in range(0, doc.pageCount):
		page = doc.loadPage(p)
		
		text += page.getText()
	
	return text



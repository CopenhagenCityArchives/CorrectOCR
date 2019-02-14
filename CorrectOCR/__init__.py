#!/usr/bin/env python

import logging
from collections import deque
from pathlib import Path
from typing import List, Iterator, TypeVar, Tuple

import fitz
import regex
from bs4.dammit import UnicodeDammit

punctuationRE = regex.compile(r'\p{punct}+')


def get_encoding(file: str) -> str:
	with open(file, 'rb') as f:
		dammit = UnicodeDammit(f.read(1024*500), ['utf-8', 'Windows-1252'])
		logging.getLogger(f'{__name__}.get_encoding').debug(f'detected {dammit.original_encoding} for {file}')
		return dammit.original_encoding


def open_for_reading(file):
	return open(file, 'r', encoding=get_encoding(file))


T = TypeVar('T')
def split_window(l: List[T], before=3, after=3) -> Iterator[Tuple[List[T], T, List[T]]]:
	a = deque(maxlen=before)
	for i in range(len(l)):
		yield list(a), l[i], l[i+1:i+1+after]
		a.append(l[i])


def ensure_new_file(path: Path):
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


def extract_text_from_pdf(filename: str):
	doc = fitz.open(filename)

	text = ''

	for p in range(0, doc.pageCount):
		page = doc.loadPage(p)

		text += page.getText()

	return text



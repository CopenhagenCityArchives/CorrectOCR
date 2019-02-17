#!/usr/bin/env python

import csv
import json
import logging
from collections import deque
from pathlib import Path
from typing import List, Iterator, TypeVar, Tuple, Any

import fitz
import regex
from bs4.dammit import UnicodeDammit


punctuationRE = regex.compile(r'\p{punct}+')




def open_for_reading(file):
	return open(file, 'r', encoding=FileAccess.get_encoding(file))


T = TypeVar('T')
def split_window(l: List[T], before=3, after=3) -> Iterator[Tuple[List[T], T, List[T]]]:
	a = deque(maxlen=before)
	for i in range(len(l)):
		yield list(a), l[i], l[i+1:i+1+after]
		a.append(l[i])


def extract_text_from_pdf(filename: str):
	doc = fitz.open(filename)

	text = ''

	for p in range(0, doc.pageCount):
		page = doc.loadPage(p)

		text += page.getText()

	return text


class FileAccess(object):
	log = logging.getLogger(f'{__name__}.FileAccess')

	JSON = 'json'
	CSV = 'csv'
	DATA = 'data'

	TOKENHEADER = ['Original', '1-best', '1-best prob.', '2-best', '2-best prob.', 
				   '3-best', '3-best prob.', '4-best', '4-best prob.', 
				   'Token type', 'Token info']
	GOLDHEADER = ['Gold'] + TOKENHEADER
	BINNEDHEADER = GOLDHEADER + ['Bin', 'Heuristic', 'Decision', 'Selection']

	@classmethod
	def get_encoding(cls, file: str) -> str:
		with open(file, 'rb') as f:
			dammit = UnicodeDammit(f.read(1024*500), ['utf-8', 'Windows-1252'])
			logging.getLogger(f'{__name__}.get_encoding').debug(f'detected {dammit.original_encoding} for {file}')
			return dammit.original_encoding

	@classmethod
	def ensure_new_file(cls, path: Path):
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

	# TODO nheaderlines
	@classmethod
	def save(cls, data: Any, path, kind=None, header=None, backup=True):
		if not kind:
			kind = cls.DATA
		if backup:
			cls.ensure_new_file(path)
		with open(path, 'w', encoding='utf-8') as f:
			if kind == cls.JSON:
				if not path.suffix == '.json':
					cls.log.error(f'Cannot save JSON to file with {path.suffix} extension! path: {path}')
					raise SystemExit(-1)
				return json.dump(data, f)
			elif kind == cls.CSV:
				if not path.suffix == '.csv':
					cls.log.error(f'Cannot save CSV to file with {path.suffix} extension! path: {path}')
					raise SystemExit(-1)
				writer = csv.DictWriter(f, header, delimiter='\t', extrasaction='ignore')
				writer.writeheader()
				return writer.writerows(data)
			else:
				return f.write(data)

	@classmethod
	def load(cls, path: Path, kind=None, default=None):
		if not kind:
			kind = cls.DATA
		if not path.is_file():
			return default
		with open_for_reading(path) as f:
			if kind == cls.JSON:
				if not path.suffix == '.json':
					cls.log.error(f'Cannot load JSON to file with {path.suffix} extension! path: {path}')
					raise SystemExit(-1)
				return json.load(f)
			elif kind == cls.CSV:
				if not path.suffix == '.csv':
					cls.log.error(f'Cannot load CSV to file with {path.suffix} extension! path: {path}')
					raise SystemExit(-1)
				return list(csv.DictReader(f, delimiter='\t'))
			else:
				return f.read()

#!/usr/bin/env python

import logging
import argparse
from pathlib import Path
from bs4 import UnicodeDammit
from collections import deque


def get_encoding(file):
	with open(file, 'rb') as f:
		dammit = UnicodeDammit(f.read(1024*500), ['utf-8', 'Windows-1252'])
		logging.getLogger(__name__+'.get_encoding').debug('detected %s for %s' % (dammit.original_encoding, file))
		return dammit.original_encoding


def open_for_reading(file):
	return open(file, 'r', encoding=get_encoding(file))


class PathType(argparse.FileType):
	def __call__(self, string):
		if not self._encoding:
			self._encoding = 'utf-8'
		if self._mode == 'd':
			p = Path(string)
			if not p.exists():
				p.mkdir()
			elif not p.is_dir():
				print('Error: Path {} exists but is not a directory!'.format(string))
				raise SystemExit(-1)
			return p
		elif self._mode == 'rc':
			p = Path(string)
			if not p.is_file():
				p.touch()
			self._mode = 'r'
			return super().__call__(string)
		elif self._mode == 'r' and string != '-':
			if not Path(string).exists():
				log = logging.getLogger(__name__)
				log.critical('Required file does not exist! Should be at: {}'.format(string))
				raise SystemExit(-1)
			self._encoding = get_encoding(string)
			return super().__call__(string)
		else:
			return super().__call__(string)


def splitwindow(l, before=3, after=3):
	a = deque(maxlen=before)
	for i in range(len(l)):
		yield list(a), l[i], l[i+1:i+1+after]
		a.append(l[i])


def ensure_new_file(path):
	counter = 0
	originalpath = path
	while Path(path).is_file():
		path = Path(path.parent, originalpath.stem + '_' + str(counter) + '.txt')
		counter += 1
	if counter > 0:
		logging.getLogger(__name__+'.ensure_new_file').info('Existing file moved to {}'.format(path))
		originalpath.rename(path)
	return originalpath

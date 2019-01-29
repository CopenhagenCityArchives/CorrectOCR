#!/usr/bin/env python

import logging
import argparse
from pathlib import Path
from bs4 import UnicodeDammit
from collections import deque


def get_encoding(file):
	with open(file, 'rb') as f:
		dammit = UnicodeDammit(f.read(1024*500), ['utf-8', 'Windows-1252'])
		logging.getLogger(f'{__name__}.get_encoding').debug(f'detected {dammit.original_encoding} for {file}')
		return dammit.original_encoding


def open_for_reading(file):
	return open(file, 'r', encoding=get_encoding(file))


class PathWrapper(object):
	def __init__(self, mode, optional=False):
		self.log = logging.getLogger(__name__)
		self._mode = mode
		self._optional = optional
		if self._mode != 'r':
			self._encoding = 'utf-8'

	def __call__(self, string):
		self._p = Path(string)
		if not self._optional:
			if self._mode == 'd':
				if not self._p.exists():
					self._p.mkdir()
				elif not self._p.is_dir():
					self.log.critical(f'Error: Path {string} exists but is not a directory!')
					raise SystemExit(-1)
			elif self._mode == 'r':
				if not self._p.exists():
					self.log.critical(f'Required file does not exist! Should be at: {string}')
					raise SystemExit(-1)
		if self._mode != 'd':
			self.open()
		return self
	
	def __getattr__(self, name):
		return getattr(self._p, name)
	
	def __fspath__(self):
		return self._p.__fspath__()
	
	def open(self):
		if self._mode == 'r':
			self._p = open_for_reading(self._p)
		elif self._mode == 'w':
			self._p = open(self._p, 'w', encoding=self._encoding)
		else:
			self.log.critical(f'Cannot open() path {self._p} with mode "{self._mode}"')

	def iterdir(self):
		if self._mode == 'd':
			return self._p.iterdir()
		else:
			self.log.critical(f'Cannot iterdir() path {self._p} with mode "{self._mode}"')


def splitwindow(l, before=3, after=3):
	a = deque(maxlen=before)
	for i in range(len(l)):
		yield list(a), l[i], l[i+1:i+1+after]
		a.append(l[i])


def ensure_new_file(path):
	counter = 0
	originalpath = path
	while Path(path).is_file():
		path = Path(path.parent, f'{originalpath.stem}_{counter:03n}.txt')
		counter += 1
	if counter > 0:
		logging.getLogger(f'{__name__}.ensure_new_file').info(f'Existing file moved to {path}')
		originalpath.rename(path)
	return path

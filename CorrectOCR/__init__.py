#!/usr/bin/env python

import logging
import argparse
import json
from pathlib import Path
from collections import deque

from bs4 import UnicodeDammit


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
		self._fh = None
		if self._mode != 'r':
			self._encoding = 'utf-8'
	
	def __str__(self):
		return f'<{self.__class__.__name__} "{self._p}" {self._mode}{" optional" if self._optional else ""}>'
	
	def __repr__(self):
		return self.__str__()

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
		if self._p.is_file():
			self.open()
		return self
	
	def __getattr__(self, name):
		if self._fh:
			return getattr(self._fh, name)
		else:
			return getattr(self._p, name)
	
	def __fspath__(self):
		return self._p.__fspath__()
	
	def open(self):
		if self._fh:
			return self._fh
		if self._mode == 'r':
			self._fh = open_for_reading(self._p)
			return self._fh
		elif self._mode == 'w':
			self._fh = open(self._p, 'w', encoding=self._encoding)
			return self._fh
		else:
			self.log.critical(f'Cannot open() path {self._p} with mode "{self._mode}"')
			raise SystemExit(-1)

	def iterdir(self):
		if self._mode == 'd':
			return self._p.iterdir()
		else:
			self.log.critical(f'Cannot iterdir() path {self._p} with mode "{self._mode}"')
			raise SystemExit(-1)

	def loadjson(self):
		if self._mode == 'd':
			self.log.critical(f'Cannot load json from directory: {self._p}')
			raise SystemExit(-1)
		elif not self._p.is_file():
			return dict()
		return json.load(self.open())

	def savejson(self, data):
		if self._mode == 'd':
			self.log.critical(f'Cannot save json from directory: {self._p}')
			raise SystemExit(-1)
		return json.dump(data, self.open())

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

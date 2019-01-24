#!/usr/bin/env python

import logging
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


def splitwindow(l, before=3, after=3):
	a = deque(maxlen=before)
	for i in range(len(l)):
		yield list(a), l[i], l[i+1:i+1+after]
		a.append(l[i])


def ensure_directories(settings):
	for k, v in vars(settings).items():
		if k[-4:] == 'Path':
			p = Path(v)
			if not p.exists():
				p.mkdir()
			elif not p.is_dir():
				print('Error: {} is set to {}, however this is not a directory!'.format(k, v))
				raise SystemExit(-1)


def ensure_new_file(path):
	counter = 0
	originalname = path
	while Path(path).is_file():
		path = originalname[:-4] + '_' + str(counter) + '.txt'
		counter += 1
	if counter > 0:
		logging.getLogger(__name__+'.ensure_new_file').info('File already exists, will instead write to ' + path)
	return path
	

def clean(settings):
	Path(settings.hmmParams).unlink()
	#TODO

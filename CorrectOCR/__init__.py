#!/usr/bin/env python

import os
from bs4 import UnicodeDammit
import logging
from collections import deque

def get_encoding(file):
	with open(file, 'rb') as f:
		dammit = UnicodeDammit(f.read(1024*500), ['utf-8', 'Windows-1252'])
		logging.getLogger(__name__+'.get_encoding').debug('detecting %s for %s' % (dammit.original_encoding, file))
		return dammit.original_encoding

def open_for_reading(file):
	return open(file, 'r', encoding=get_encoding(file))

def splitwindow(l, before=3, after=3):
	a = deque(maxlen=before)
	for i in range(len(l)):
		yield list(a), l[i], l[i+1:i+1+after]
		a.append(l[i])

def clean(settings):
	os.remove(settings.hmmParams)
	#TODO
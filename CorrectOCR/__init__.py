#!/usr/bin/env python

import os
from bs4 import UnicodeDammit
import logging

def get_encoding(file):
	with open(file, 'rb') as f:
		dammit = UnicodeDammit(f.read(1024*500), ['utf-8', 'Windows-1252'])
		logging.getLogger(__name__+'.get_encoding').debug('detecting %s for %s' % (dammit.original_encoding, file))
		return dammit.original_encoding

def open_for_reading(file):
	return open(file, 'r', encoding=get_encoding(file))

def clean(settings):
	os.remove(settings.hmmParams)
	#TODO
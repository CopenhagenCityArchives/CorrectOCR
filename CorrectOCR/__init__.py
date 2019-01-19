#!/usr/bin/env python

import chardet

def get_encoding(file):
	with open(file, 'rb') as f:
		detection = chardet.detect(f.read(1024*50))
		return detection['encoding']

#!/usr/bin/env python

from . import dictionary
from . import model

defaults = """
[settings]
fullAlignments = train/parallelAligned/fullAlignments/
misreadCounts = train/parallelAligned/misreadCounts/
misreads = train/parallelAligned/misreads/
characterSet = ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz
"""

if __name__=='__main__':
	import configparser
	import argparse
	
	config = configparser.RawConfigParser()
	config.optionxform = lambda option: option
	config.read_string(defaults)
	config.read(['CorrectOCR.ini'], encoding='utf-8')
	
	settings = argparse.Namespace(**dict(config.items('settings')))
	
	mainparser = argparse.ArgumentParser(description='Correct OCR')
	
	subparsers = mainparser.add_subparsers(dest='command', help='Choose command')
	
	dictparser = subparsers.add_parser('build_dictionary', help='Build dictionary')
	dictparser.add_argument('output', type=argparse.FileType('w', encoding='utf-8'))
	dictparser.add_argument('files', nargs='*')
	dictparser.set_defaults(func=dictionary.build_dictionary)
	
	alignparser = subparsers.add_parser('align', help='Create alignments')
	alignparser.add_argument('--filepair', action='append', nargs=2, dest='filepairs', type=argparse.FileType('r', encoding='Windows-1252')) # TODO guess encoding?
	alignparser.set_defaults(func=model.align_pairs)
	
	alignparser = subparsers.add_parser('build_model', help='Build model')
	alignparser.set_defaults(func=model.build_model)

	args = mainparser.parse_args(namespace=settings)
	
	args.func(args)
	
	exit() # TODO exit code?
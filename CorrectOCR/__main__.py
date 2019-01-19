#!/usr/bin/env python

defaults = """
[paths]
fullAlignments = train/parallelAligned/fullAlignments/
misreadCounts = train/parallelAligned/misreadCounts/
misreads = train/parallelAligned/misreads/

[data]
characterSet = ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz
"""

if __name__=='__main__':
	import configparser
	import argparse
	import os
	import re
	
	config = configparser.RawConfigParser()
	config.read_string(defaults)
	if os.path.exists('CorrectOCR.ini'):
		config.read_file(open('CorrectOCR.ini', encoding='utf-8'))
	
	mainparser = argparse.ArgumentParser(description='Correct OCR')
	
	subparsers = mainparser.add_subparsers(dest='command', help='Choose command')
	
	alignparser = subparsers.add_parser('build_dictionary', help='Build dictionary')
	alignparser.add_argument('output', type=argparse.FileType('w', encoding='utf-8'))
	alignparser.add_argument('files', nargs='*')
	
	alignparser = subparsers.add_parser('align', help='Create alignments')
	alignparser.add_argument('--filepair', action='append', nargs=2, dest='filepairs', type=argparse.FileType('r', encoding='Windows-1252')) # TODO guess encoding?
	#alignparser.set_defaults(func=align)
	
	alignparser = subparsers.add_parser('build_model', help='Build model')

	args = mainparser.parse_args()
	
	#mainparser.func(args)
	
	if args.command == 'build_dictionary':
		from . import dictionary
		dictionary.build_dictionary(re.sub(r'\W+', r'', config['data']['characterSet']), args.output, args.files)
	elif args.command == 'align':
		from . import model
		for pair in args.filepairs:
			basename = os.path.splitext(os.path.basename(pair[0].name))[0]
			model.align(config, basename, pair[0].read(), pair[1].read())
	elif args.command == 'build_model':
		from . import model
		model.build_model(config['data']['characterSet'])


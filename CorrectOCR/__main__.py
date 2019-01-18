#!/usr/bin/env python

defaults = """
[paths]
fullAlignments = train/parallelAligned/fullAlignments/
misreadCounts = train/parallelAligned/misreadCounts/
misreads = train/parallelAligned/misreads/

[data]
characterSet = ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz
"""

def align(config, basename, a, b, words=False):
	import difflib
	import collections
	import json
	
	matcher = difflib.SequenceMatcher(autojunk=False) #isjunk=lambda x: junkre.search(x))
	
	if words:
		a = a.split()
		b = b.split()
	matcher.set_seqs(a, b)
		
	fullAlignments = []
	misreadCounts = collections.defaultdict(collections.Counter)
	misreads = []
	
	for tag, i1, i2, j1, j2 in matcher.get_opcodes():
		if tag != 'equal':
			if max(j2-j1, i2-i1) > 4:							# skip moved lines from overeager contributors :)
				continue
			fullAlignments.append([a[i1:i2], b[j1:j2]])
			misreadCounts[b[j1:j2]][a[i1:i2]] += 1
			misreads.append([b[j1:j2], a[i1:i2], j1, i1])
			print('{:7}   a[{}:{}] --> b[{}:{}] {!r:>8} --> {!r}'.format(tag, i1, i2, j1, j2, a[i1:i2], b[j1:j2]))
		else:
			for char in a[i1:i2]:
				fullAlignments.append([char, char])
				misreadCounts[char][char] += 1
	
	#for char,reads in misreadCounts.copy().items():
	#	if char in reads and len(reads) == 1: # remove characters that were read 100% correctly
	#		del misreadCounts[char]
	
	with open(config['paths']['fullAlignments'] + basename + '_full_alignments.json', 'w', encoding='utf-8') as f:
		json.dump(fullAlignments, f)
		f.close()
	
	with open(config['paths']['misreadCounts'] + basename + '_misread_counts.json', 'w', encoding='utf-8') as f:
		json.dump(misreadCounts, f)
		print(misreadCounts)
		f.close()
	
	with open(config['paths']['misreads'] + basename + '_misreads.json', 'w', encoding='utf-8') as f:
		json.dump(misreads, f)
		f.close()

			
if __name__=='__main__':
	import configparser
	import argparse
	import os
	
	config = configparser.ConfigParser()
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
		dictionary.build_dictionary(config['data']['characterSet'], args.output, args.files)
	elif args.command == 'align':
		for pair in args.filepairs:
			basename = os.path.splitext(os.path.basename(pair[0].name))[0]
			align(config, basename, pair[0].read(), pair[1].read())
	elif args.command == 'build_model':
		print('Not implemented. Use model_builder.py instead.')

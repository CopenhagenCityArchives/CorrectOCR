#!/usr/bin/env python

from . import get_encoding, clean
from . import dictionary
from . import model
from . import decoder
from . import tuner

defaults = """
[settings]
fullAlignments = train/parallelAligned/fullAlignments/
misreadCounts = train/parallelAligned/misreadCounts/
misreads = train/parallelAligned/misreads/
characterSet = ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz
hmmParams = train/hmm_parameters.json
"""

if __name__=='__main__':
	import logging
	import sys

	logging.basicConfig(
		stream=sys.stdout,
		format='%(asctime)s - %(levelname)8s - %(name)s - %(message)s',
		level=logging.DEBUG #TODO argparse
	)
	
	import configparser
	import argparse
	
	class FileType(argparse.FileType):
		def __call__(self, string):
			if self._mode == 'r' and string != '-':
				self._encoding = get_encoding(string)
				return super().__call__(string)
			else:
				return super().__call__(string)
	
	config = configparser.RawConfigParser()
	config.optionxform = lambda option: option
	config.read_string(defaults)
	config.read(['CorrectOCR.ini'], encoding='utf-8')
	
	settings = argparse.Namespace(**dict(config.items('settings')))
	
	mainparser = argparse.ArgumentParser(description='Correct OCR')
	
	subparsers = mainparser.add_subparsers(dest='command', help='Choose command', required=True)
	
	dictparser = subparsers.add_parser('build_dictionary', help='Build dictionary')
	dictparser.add_argument('output', type=FileType('w', encoding='utf-8'))
	dictparser.add_argument('files', nargs='*')
	dictparser.set_defaults(func=dictionary.build_dictionary)
	
	alignparser = subparsers.add_parser('align', help='Create alignments')
	alignparser.add_argument('--filepair', action='append', nargs=2, dest='filepairs', type=FileType('r'))
	alignparser.set_defaults(func=model.align_pairs)
	
	alignparser = subparsers.add_parser('build_model', help='Build model')
	alignparser.set_defaults(func=model.build_model)
	
	decodeparser = subparsers.add_parser('decode', help='Decode')
	decodeparser.add_argument('input_file', help='text file to decode')
	decodeparser.add_argument('--dictionary', help='dictionary')
	decodeparser.set_defaults(func=decoder.decode)
	
	tunerparser = subparsers.add_parser('tune', help='Tune settings prep')
	tunerparser.add_argument('-d', '--dictionary', help='path to dictionary file')
	tunerparser.add_argument('-c', '--caseInsensitive', action='store_true', help='case sensitivity')
	tunerparser.add_argument('-k', default=4, help='number of decoded candidates in input, default 4')
	tunerparser.add_argument('-v', '--csvdir', default='train/devDecoded', help='path for directory of decoding CSVs')
	tunerparser.add_argument('-o', '--outfile', default='resources/report.txt', help='output file name')
	tunerparser.set_defaults(func=tuner.tune)
	
	settingsparser = subparsers.add_parser('make_settings', help='Make settings')
	settingsparser.add_argument('--report', default='resources/report.txt', type=FileType('r'))
	settingsparser.add_argument('-o', '--outfile', default='resources/settings.txt', help='output file name')
	settingsparser.set_defaults(func=tuner.make_settings)
	
	cleanparser = subparsers.add_parser('clean', help='Clean files')
	cleanparser.set_defaults(func=clean)
	
	args = mainparser.parse_args(namespace=settings)
	
	args.func(args)
	
	exit() # TODO exit code?
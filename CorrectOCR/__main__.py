#!/usr/bin/env python

import logging
import sys
import configparser
import argparse

from . import get_encoding, clean
from . import dictionary
from . import model
from . import decoder
from . import tuner
from . import correcter

defaults = """
[settings]
characterSet = ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz
nheaderlines = 0
fullAlignmentsPath = train/parallelAligned/fullAlignments/
misreadCountsPath = train/parallelAligned/misreadCounts/
misreadsPath = train/parallelAligned/misreads/
hmmParamsPath = train/hmm_parameters.json
hmmTrainPath = train/HMMtrain/
decodedPath = ./decoded/
devDecodedPath = ./train/devDecoded/
originalPath = ./original/
dictionaryPath = ./resources/dictionary.txt
correctedPath = ./corrected/
newWordsPath = ./resources/newwords/
heuristicSettingsPath = ./resources/settings.txt
memoizedPath =  ./resources/memoized_corrections.txt
correctionTrackingPath = ./resources/correction_tracking.txt
"""

logging.basicConfig(
	stream=sys.stdout,
	format='%(asctime)s - %(levelname)8s - %(name)s - %(message)s',
	level=logging.DEBUG #TODO argparse
)
log = logging.getLogger(__name__)

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

settings = dict(config.items('settings'))

mainparser = argparse.ArgumentParser(description='Correct OCR')

subparsers = mainparser.add_subparsers(dest='command', help='Choose command', required=True)

dictparser = subparsers.add_parser('build_dictionary', help='Build dictionary')
dictparser.add_argument('output', type=FileType('w', encoding='utf-8'))
dictparser.add_argument('files', nargs='*')
dictparser.set_defaults(func=dictionary.build_dictionary, **settings)

alignparser = subparsers.add_parser('align', help='Create alignments')
alignparser.add_argument('--filepair', action='append', nargs=2, dest='filepairs', type=FileType('r'))
alignparser.set_defaults(func=model.align_pairs, **settings)

alignparser = subparsers.add_parser('build_model', help='Build model')
alignparser.add_argument('-l', '--nheaderlines', type=int, help='number of header lines in original corpus texts')
alignparser.add_argument('--smoothingParameter', default=0.0001, help='Smoothing parameter for HMM')
alignparser.add_argument('--hmmTrainPath', metavar='PATH', help='Path to misread count files')
alignparser.add_argument('--correctedPath', metavar='PATH', help='Path to corrected files')
alignparser.set_defaults(func=model.build_model, **settings)

decodeparser = subparsers.add_parser('decode', help='Decode')
decodeparser.add_argument('input_file', help='text file to decode')
decodeparser.add_argument('--dictionary', help='dictionary')
decodeparser.set_defaults(func=decoder.decode, **settings)

tunerparser = subparsers.add_parser('tune', help='Tune settings prep')
tunerparser.add_argument('-d', '--dictionary', help='path to dictionary file')
tunerparser.add_argument('-c', '--caseInsensitive', action='store_true', help='case sensitivity')
tunerparser.add_argument('-k', default=4, help='number of decoded candidates in input, default 4')
tunerparser.add_argument('-v', '--devDecodedPath', help='path for directory of decoding CSVs')
tunerparser.add_argument('-o', '--outfile', default='resources/report.txt', help='output file name')
tunerparser.set_defaults(func=tuner.tune, **settings)

settingsparser = subparsers.add_parser('make_settings', help='Make settings')
settingsparser.add_argument('--report', default='resources/report.txt', type=FileType('r'))
settingsparser.add_argument('-o', '--outfile', default=settings['heuristicSettingsPath'], help='output file name')
settingsparser.set_defaults(func=tuner.make_settings, **settings)

correctparser = subparsers.add_parser('correct', help='Make settings')
correctparser.add_argument('fileid', help='input ID (without path or extension)')
correctparser.add_argument('-p', '--originalPath', metavar='PATH', help='original plain text corpus directory location')
correctparser.add_argument('-d', '--dictionaryPath', metavar='PATH', help='path to dictionary file')
correctparser.add_argument('-c', '--caseInsensitive', action='store_true', default=False, help='case sensitivity')
correctparser.add_argument('-v', '--decodedPath', metavar='PATH', help='directory containing HMM decodings')
correctparser.add_argument('-s', '--heuristicSettingsPath', metavar='PATH', type=FileType('r'), help='path to heuristic settings file')
correctparser.add_argument('-k', default=4, help='number of decoded candidates in input')
correctparser.add_argument('-r', '--dehyphenate', action='store_true', help='repair hyphenation')
correctparser.add_argument('-o', '--correctfilename', metavar='FILENAME', help='path for corrected output file name')
correctparser.add_argument('-w', '--dictpotentialname', metavar='FILENAME', type=FileType('r'), help='path for file of new words to consider for dictionary')
correctparser.add_argument('-t', '--learningfilename', metavar='FILENAME', type=FileType('r'), help='file to track annotations')
correctparser.add_argument('-m', '--memofilename', metavar='FILENAME', type=FileType('r'), help='file of memorised deterministic corrections')
correctparser.add_argument('-l', '--nheaderlines', type=int, help='number of header lines in original corpus texts')
correctparser.set_defaults(func=correcter.correct, **settings)

cleanparser = subparsers.add_parser('clean', help='Clean files')
cleanparser.set_defaults(func=clean, **settings)

args = mainparser.parse_args()

log.info('Settings for this invocation: ' + str(vars(args)))
args.func(args)

exit() # TODO exit code?

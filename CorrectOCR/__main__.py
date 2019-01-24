#!/usr/bin/env python

import logging
import sys
import configparser
import argparse
from pathlib import Path

from . import get_encoding, ensure_directories, clean
from . import dictionary
from . import model
from . import decoder
from . import heuristics
from . import correcter

defaults = """
[settings]
characterSet = ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz
nheaderlines = 0
correctedPath = corrected/
decodedPath = decoded/
originalPath = original/
correctionTrackingFile = resources/correction_tracking.txt
dictionaryFile = resources/dictionary.txt
memoizedCorrectionsFile = resources/memoized_corrections.txt
multiCharacterErrorFile = resources/multicharacter_errors.json
newWordsPath = resources/newwords/
reportFile = resources/report.txt
heuristicSettingsFile = resources/settings.txt
devDecodedPath = train/devDecoded/
hmmParamsFile = train/hmm_parameters.json
hmmTrainPath = train/HMMtrain/
fullAlignmentsPath = train/parallelAligned/fullAlignments/
misreadCountsPath = train/parallelAligned/misreadCounts/
misreadsPath = train/parallelAligned/misreads/
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

rootparser = argparse.ArgumentParser(description='Correct OCR')

commonparser = argparse.ArgumentParser(add_help=False)
commonparser.add_argument('-d', '--dictionaryFile', metavar='FILE', type=FileType('r'), help='Path to dictionary file')


subparsers = rootparser.add_subparsers(dest='command', help='Choose command', required=True)

dictparser = subparsers.add_parser('build_dictionary', parents=[commonparser], help='Build dictionary')
dictparser.add_argument('files', type=Path, nargs='*')
dictparser.set_defaults(func=dictionary.build_dictionary, **settings)

alignparser = subparsers.add_parser('align', parents=[commonparser], help='Create alignments')
group = alignparser.add_mutually_exclusive_group(required=True)
group.add_argument('--filePair', action='append', metavar='FILE', nargs=2, dest='filepairs', type=FileType('r'), help='Align pair of files')
group.add_argument('--allPairs', action='store_true', help='Align all pairs in original/corrected paths')
alignparser.add_argument('-p', '--originalPath', type=Path, metavar='PATH', help='original plain text corpus directory location')
alignparser.add_argument('-o', '--correctedPath', type=Path, metavar='PATH', help='Path to output corrected files')
alignparser.add_argument('--fullAlignmentsPath', type=Path, metavar='PATH', help='Path to output full alignments')
alignparser.add_argument('--misreadCountsPath', type=Path, metavar='PATH', help='Path to output misread counts')
alignparser.add_argument('--misreadsPath', type=Path, metavar='PATH', help='Path to output misreads')
alignparser.set_defaults(func=model.align_pairs, **settings)

alignparser = subparsers.add_parser('build_model', parents=[commonparser], help='Build model')
alignparser.add_argument('-l', '--nheaderlines', type=int, help='number of header lines in original corpus texts')
alignparser.add_argument('--smoothingParameter', default=0.0001, help='Smoothing parameter for HMM')
alignparser.add_argument('--hmmTrainPath', type=Path, metavar='PATH', help='Path to misread count files')
alignparser.add_argument('--correctedPath', type=Path, metavar='PATH', help='Path to corrected files')
alignparser.set_defaults(func=model.build_model, **settings)

decodeparser = subparsers.add_parser('decode', parents=[commonparser], help='Decode')
decodeparser.add_argument('input_file', help='text file to decode')
decodeparser.add_argument('-k', default=4, help='number of decoded candidates in input')
decodeparser.add_argument('-l', '--nheaderlines', type=int, help='number of header lines in original corpus texts')
decodeparser.set_defaults(func=decoder.decode, **settings)

tunerparser = subparsers.add_parser('make_report', parents=[commonparser], help='Make heuristics report')
tunerparser.add_argument('-c', '--caseInsensitive', action='store_true', help='case sensitivity')
tunerparser.add_argument('-k', default=4, help='number of decoded candidates in input, default 4')
tunerparser.add_argument('-v', '--devDecodedPath', type=Path, metavar='PATH', help='path for directory of decoding CSVs')
tunerparser.add_argument('-o', '--outfile', default='resources/report.txt', help='output file name')
tunerparser.set_defaults(func=heuristics.make_report, **settings)

settingsparser = subparsers.add_parser('make_settings', parents=[commonparser], help='Make heuristics settings')
settingsparser.add_argument('--reportFile', type=FileType('r'))
settingsparser.add_argument('-o', '--outfile', default=settings['heuristicSettingsFile'], help='output file name')
settingsparser.set_defaults(func=heuristics.make_settings, **settings)

correctparser = subparsers.add_parser('correct', parents=[commonparser], help='Make settings')
correctparser.add_argument('fileid', help='input ID (without path or extension)')
correctparser.add_argument('-p', '--originalPath', type=Path, metavar='PATH', help='original plain text corpus directory location')
correctparser.add_argument('-o', '--correctedPath', type=Path, metavar='PATH', help='Path to output corrected files')
correctparser.add_argument('-v', '--decodedPath', type=Path, metavar='PATH', help='directory containing HMM decodings')
correctparser.add_argument('-s', '--heuristicSettingsFile', metavar='FILE', type=FileType('r'), help='path to heuristic settings file')
correctparser.add_argument('-c', '--caseInsensitive', action='store_true', default=False, help='case sensitivity')
correctparser.add_argument('-k', default=4, help='number of decoded candidates in input')
correctparser.add_argument('-r', '--dehyphenate', action='store_true', help='repair hyphenation')
correctparser.add_argument('-w', '--newWordsPath', type=Path, metavar='PATH', help='path for file of new words to consider for dictionary')
correctparser.add_argument('-t', '--correctionTrackingFile', metavar='FILENAME', type=FileType('r'), help='file to track annotations')
correctparser.add_argument('-m', '--memoizedCorrectionsFile', metavar='FILE', type=FileType('r'), help='file of memorised deterministic corrections')
correctparser.add_argument('-l', '--nheaderlines', type=int, help='number of header lines in original corpus texts')
correctparser.set_defaults(func=correcter.correct, **settings)

cleanparser = subparsers.add_parser('clean', help='Clean files')
cleanparser.set_defaults(func=clean, **settings)

args = rootparser.parse_args()

ensure_directories(args)

log.info('Settings for this invocation: ' + str(vars(args)))
args.func(args)

exit() # TODO exit code?

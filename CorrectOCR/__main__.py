#!/usr/bin/env python

import logging
import os
import sys
import configparser
import argparse
from pathlib import Path

from . import get_encoding, ensure_directories, PathType
from . import dictionary
from . import model
from . import decoder
from . import heuristics
from . import correcter

defaults = """
[settings]
characterSet = ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz
nheaderlines = 0
k = 4
correctedPath = corrected/
decodedPath = decoded/
originalPath = original/
correctionTrackingFile = resources/correction_tracking.json
dictionaryFile = resources/dictionary.txt
memoizedCorrectionsFile = resources/memoized_corrections.json
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

# windows/mobaxterm/py3.6 fix:
if os.name == 'nt':
	import io
	sys.stdout = io.TextIOWrapper(sys.stdout.buffer,encoding='utf8')

logging.basicConfig(
	stream=sys.stdout,
	format='%(asctime)s - %(levelname)8s - %(name)s - %(message)s',
	level=logging.DEBUG
)
log = logging.getLogger(__name__)

config = configparser.RawConfigParser()
config.optionxform = lambda option: option
config.read_string(defaults)
config.read(['CorrectOCR.ini'], encoding='utf-8')

settings = dict(config.items('settings'))

rootparser = argparse.ArgumentParser(description='Correct OCR')

commonparser = argparse.ArgumentParser(add_help=False)
commonparser.add_argument('--dictionaryFile', metavar='FILE', type=PathType('rc'), help='Path to dictionary file')
commonparser.add_argument('--caseInsensitive', action='store_true', default=False, help='Use case insensitive dictionary comparisons')
commonparser.add_argument('-k', type=int, default=4, help='Number of k-best candidates')
commonparser.add_argument('--nheaderlines', type=int, metavar='N', help='number of header lines in original corpus texts')
commonparser.add_argument('--originalPath', type=PathType('d'), metavar='PATH', help='original plain text corpus directory location')
commonparser.add_argument('--correctedPath', type=PathType('d'), metavar='PATH', help='Path to output corrected files')
commonparser.add_argument('--decodedPath', type=PathType('d'), metavar='PATH', help='directory containing HMM decodings')
commonparser.add_argument('--fullAlignmentsPath', type=PathType('d'), metavar='PATH', help='Path to output full alignments')
commonparser.add_argument('--misreadCountsPath', type=PathType('d'), metavar='PATH', help='Path to output misread counts')
commonparser.add_argument('--misreadsPath', type=PathType('d'), metavar='PATH', help='Path to output misreads')

if sys.version_info >= (3, 7):
	subparsers = rootparser.add_subparsers(dest='command', help='Choose command', required=True)
else:
	subparsers = rootparser.add_subparsers(dest='command', help='Choose command')

dictparser = subparsers.add_parser('build_dictionary', parents=[commonparser], help='Build dictionary')
dictparser.add_argument('files', type=PathType('d'), nargs='*')
dictparser.set_defaults(func=dictionary.build_dictionary, **settings)

alignparser = subparsers.add_parser('align', parents=[commonparser], help='Create alignments')
group = alignparser.add_mutually_exclusive_group(required=True)
group.add_argument('--fileid', help='input ID (without path or extension)')
group.add_argument('--allPairs', action='store_true', help='Align all pairs in original/corrected paths')
alignparser.set_defaults(func=model.align, **settings)

alignparser = subparsers.add_parser('build_model', parents=[commonparser], help='Build model')
alignparser.add_argument('--smoothingParameter', default=0.0001, metavar='N[.N]', help='Smoothing parameter for HMM')
alignparser.add_argument('--hmmTrainPath', type=PathType('d'), metavar='PATH', help='Path to misread count files')
alignparser.set_defaults(func=model.build_model, **settings)

decodeparser = subparsers.add_parser('decode', parents=[commonparser], help='Decode')
decodeparser.add_argument('input_file', help='text file to decode')
decodeparser.add_argument('--multiCharacterErrorFile', metavar='FILE', type=PathType('d'), help='Path to multichar file')
decodeparser.set_defaults(func=decoder.decode, **settings)

tunerparser = subparsers.add_parser('make_report', parents=[commonparser], help='Make heuristics report')
tunerparser.add_argument('--devDecodedPath', type=PathType('d'), metavar='PATH', help='path for directory of decoding CSVs')
tunerparser.add_argument('--outfile', default=settings['reportFile'], help='output file name')
tunerparser.set_defaults(func=heuristics.make_report, **settings)

settingsparser = subparsers.add_parser('make_settings', parents=[commonparser], help='Make heuristics settings')
settingsparser.add_argument('--reportFile', type=PathType('r'))
settingsparser.add_argument('--outfile', default=settings['heuristicSettingsFile'], help='output file name')
settingsparser.set_defaults(func=heuristics.make_settings, **settings)

correctparser = subparsers.add_parser('correct', parents=[commonparser], help='Make settings')
correctparser.add_argument('fileid', help='input ID (without path or extension)')
correctparser.add_argument('--heuristicSettingsFile', metavar='FILE', type=PathType('r'), help='path to heuristic settings file')
correctparser.add_argument('--dehyphenate', action='store_true', help='repair hyphenation')
correctparser.add_argument('--newWordsPath', type=PathType('d'), metavar='PATH', help='path for file of new words to consider for dictionary')
correctparser.add_argument('--correctionTrackingFile', metavar='FILE', type=PathType('rc'), help='file to track annotations')
correctparser.add_argument('--memoizedCorrectionsFile', metavar='FILE', type=PathType('rc'), help='file of memorised deterministic corrections')
correctparser.set_defaults(func=correcter.correct, **settings)

args = rootparser.parse_args()

ensure_directories(args)

log.info(u'Settings for this invocation: {}'.format(vars(args)))
args.func(args)

exit()

#!/usr/bin/env python

import logging
import os
import sys
import configparser
import argparse
from pathlib import Path

import progressbar

from . import get_encoding, PathType
from . import dictionary
from . import model
from . import tokenizer
from . import heuristics
from . import correcter

defaults = """
[settings]
characterSet = ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz
nheaderlines = 0
k = 4
correctedPath = corrected/
goldPath = gold/
originalPath = original/
correctionTrackingFile = resources/correction_tracking.json
dictionaryFile = resources/dictionary.txt
memoizedCorrectionsFile = resources/memoized_corrections.json
multiCharacterErrorFile = resources/multicharacter_errors.json
reportFile = resources/report.txt
heuristicSettingsFile = resources/settings.txt
goldTokenPath = training/goldTokens/
hmmParamsFile = training/hmm_parameters.json
fullAlignmentsPath = training/parallelAligned/fullAlignments/
misreadCountsPath = training/parallelAligned/misreadCounts/
wordAlignmentsPath = training/parallelAligned/wordAlignments/
tokenPath = training/tokens/
"""

# windows/mobaxterm/py3.6 fix:
if os.name == 'nt':
	import io
	sys.stdout = io.TextIOWrapper(sys.stdout.buffer,encoding='utf8')

progressbar.streams.wrap_stderr()

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
commonparser.add_argument('--caseInsensitive', action='store_true', default=False, help='Use case insensitive dictionary comparisons')
commonparser.add_argument('-k', type=int, default=4, help='Number of k-best candidates')
commonparser.add_argument('--nheaderlines', metavar='N', type=int, help='number of header lines in original corpus texts')
commonparser.add_argument('--force', action='store_true', default=False, help='Force command to run')

commonparser.add_argument('--correctedPath', metavar='PATH', type=PathType('d'), help='Path to output corrected files')
commonparser.add_argument('--correctionTrackingFile', metavar='FILE', type=PathType('rc'), help='file to track annotations')
commonparser.add_argument('--dictionaryFile', metavar='FILE', type=PathType('rc'), help='Path to dictionary file')
commonparser.add_argument('--fullAlignmentsPath', metavar='PATH', type=PathType('d'), help='Path to output full alignments')
commonparser.add_argument('--goldPath', metavar='PATH', type=PathType('d'), help='Path to known correct files (aka. "gold" files)')
commonparser.add_argument('--goldTokenPath', metavar='PATH', type=PathType('d'), help='Path for directory containing tokens with added k-best')
commonparser.add_argument('--heuristicSettingsFile', metavar='FILE', type=PathType('r'), help='path to heuristic settings file')
commonparser.add_argument('--memoizedCorrectionsFile', metavar='FILE', type=PathType('rc'), help='file of memorised deterministic corrections')
commonparser.add_argument('--misreadCountsPath', metavar='PATH', type=PathType('d'), help='Path to output misread counts')
commonparser.add_argument('--multiCharacterErrorFile', metavar='FILE', type=PathType('rc'), help='Path to multichar file')
commonparser.add_argument('--originalPath', metavar='PATH', type=PathType('d'), help='original plain text corpus directory location')
commonparser.add_argument('--tokenPath', metavar='PATH', type=PathType('d'), help='directory containing tokens')
commonparser.add_argument('--wordAlignmentsPath', type=PathType('d'), metavar='PATH', help='Path to word-level alignments')

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
alignparser.set_defaults(func=model.build_model, **settings)

tokenizerparser = subparsers.add_parser('tokenize', parents=[commonparser], help='Tokenize and add k-best guesses')
tokenizerparser.add_argument('fileid', help='input ID (without path or extension)')
tokenizerparser.set_defaults(func=tokenizer.tokenize, **settings)

tunerparser = subparsers.add_parser('make_report', parents=[commonparser], help='Make heuristics report')
tunerparser.add_argument('reportFile', default=settings['reportFile'], help='output file name')
tunerparser.set_defaults(func=heuristics.make_report, **settings)

settingsparser = subparsers.add_parser('make_settings', parents=[commonparser], help='Make heuristics settings')
settingsparser.add_argument('--reportFile', type=PathType('r'))
settingsparser.add_argument('--outfile', default=settings['heuristicSettingsFile'], help='output file name')
settingsparser.set_defaults(func=heuristics.make_settings, **settings)

correctparser = subparsers.add_parser('correct', parents=[commonparser], help='Make settings')
correctparser.add_argument('fileid', help='input ID (without path or extension)')
correctparser.add_argument('--dehyphenate', action='store_true', help='repair hyphenation')
correctparser.set_defaults(func=correcter.correct, **settings)

args = rootparser.parse_args()

log.info(u'Settings for this invocation: {}'.format(vars(args)))
args.func(args)

exit()

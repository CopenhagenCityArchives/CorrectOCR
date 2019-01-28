#!/usr/bin/env python

import logging
import os
import sys
import configparser
import argparse
from pathlib import Path
from pprint import pformat

import progressbar

from . import get_encoding, PathType
from . import dictionary
from . import model
from . import tokenizer
from . import heuristics
from . import correcter

defaults = """
[configuration]
characterSet = ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz
correctedPath = corrected/
goldPath = gold/
originalPath = original/
correctionTrackingFile = resources/correction_tracking.json
dictionaryFile = resources/dictionary.txt
hmmParamsFile = resources/hmm_parameters.json
memoizedCorrectionsFile = resources/memoized_corrections.json
multiCharacterErrorFile = resources/multicharacter_errors.json
reportFile = resources/report.txt
heuristicSettingsFile = resources/settings.txt
trainingPath = training/
"""

progname = 'CorrectOCR'

# windows/mobaxterm/py3.6 fix:
if os.name == 'nt':
	import io
	sys.stdout = io.TextIOWrapper(sys.stdout.buffer,encoding='utf8')

progressbar.streams.wrap_stderr()

config = configparser.RawConfigParser()
config.optionxform = lambda option: option
config.read_string(defaults)
config.read(['CorrectOCR.ini'], encoding='utf-8')

configuration = dict(config.items('configuration'))

rootparser = argparse.ArgumentParser(prog=progname, description='Correct OCR')

commonparser = argparse.ArgumentParser(add_help=False)
commonparser.add_argument('-k', type=int, default=4, help='Number of k-best candidates to use for tokens (default: 4)')
commonparser.add_argument('--nheaderlines', metavar='N', type=int, default=0, help='Number of lines in corpus file headers (default: 0)')

commonparser.add_argument('--dictionaryFile', metavar='FILE', type=PathType('rc'), help='Path to dictionary file')
commonparser.add_argument('--caseInsensitive', action='store_true', default=False, help='Use case insensitive dictionary comparisons')

commonparser.add_argument('--trainingPath', metavar='PATH', type=PathType('d'), help='Path for generated training files')

commonparser.add_argument('--force', action='store_true', default=False, help='Force command to run')

loglevels = dict(logging._nameToLevel)
del loglevels['NOTSET']
del loglevels['WARN']
commonparser.add_argument('--loglevel', type=str, help='Log level', choices=loglevels.keys(), default='INFO')

if sys.version_info >= (3, 7):
	subparsers = rootparser.add_subparsers(dest='command', help='Choose command', required=True)
else:
	subparsers = rootparser.add_subparsers(dest='command', help='Choose command')

dictparser = subparsers.add_parser('build_dictionary', parents=[commonparser], help='Build dictionary')
dictparser.add_argument('dictionaryCorpus', type=PathType('d'), help='Direcotry of files to split into words and add to dictionary (TXT or PDF format)')
dictparser.set_defaults(func=dictionary.build_dictionary, **configuration)

alignparser = subparsers.add_parser('align', parents=[commonparser], help='Create alignments')
group = alignparser.add_mutually_exclusive_group(required=True)
group.add_argument('--fileid', help='Input file ID (filename without path or extension)')
group.add_argument('--allPairs', action='store_true', help='Align all pairs in original/corrected paths')
alignparser.add_argument('--originalPath', metavar='PATH', type=PathType('d'), help='Path to directory of original, uncorrected files')
alignparser.add_argument('--goldPath', metavar='PATH', type=PathType('d'), help='Path to directory of known correct "gold" files')
alignparser.set_defaults(func=model.align, **configuration)

modelparser = subparsers.add_parser('build_model', parents=[commonparser], help='Build model')
modelparser.add_argument('--smoothingParameter', default=0.0001, metavar='N[.N]', help='Smoothing parameters for HMM (default: 0.0001)')
modelparser.add_argument('--goldPath', metavar='PATH', type=PathType('d'), help='Path to directory of known correct files (aka. "gold" files)')
modelparser.add_argument('--hmmParamsFile', metavar='FILE', type=PathType('w'), help='Path to output HMM parameters (JSON format)')
modelparser.set_defaults(func=model.build_model, **configuration)

tokenizerparser = subparsers.add_parser('tokenize', parents=[commonparser], help='Tokenize and add k-best guesses')
tokenizerparser.add_argument('--fileid', required=True, help='Input file ID (filename without path or extension)')
tokenizerparser.add_argument('--hmmParamsFile', metavar='FILE', type=PathType('r'), help='Path to HMM parameters (generated from alignment files via build_model command)')
tokenizerparser.add_argument('--originalPath', metavar='PATH', type=PathType('d'), help='Path to directory of original, uncorrected files')
tokenizerparser.add_argument('--goldPath', metavar='PATH', type=PathType('d'), help='Path to directory of known correct files (aka. "gold" files)')
tokenizerparser.add_argument('--multiCharacterErrorFile', metavar='FILE', type=PathType('rc'), help='Path to output multi-character error file (JSON format)')
tokenizerparser.set_defaults(func=tokenizer.tokenize, **configuration)

tunerparser = subparsers.add_parser('make_report', parents=[commonparser], help='Make heuristics report')
tunerparser.add_argument('--reportFile', metavar='FILE', type=PathType('w'), help='Path to output heuristics report (TXT file)')
tunerparser.set_defaults(func=heuristics.make_report, **configuration)

settingsparser = subparsers.add_parser('make_settings', parents=[commonparser], help='Make heuristics settings')
settingsparser.add_argument('--reportFile', metavar='FILE', type=PathType('r'), help='Path to annotated heuristics report (generated from tokens via make_report command)')
settingsparser.add_argument('--heuristicSettingsFile', metavar='FILE', type=PathType('w') , help='Path to output heuristics settings (TXT format)')
settingsparser.set_defaults(func=heuristics.make_settings, **configuration)

correctparser = subparsers.add_parser('correct', parents=[commonparser], help='Run assisted correction interface')
correctparser.add_argument('--fileid', required=True, help='Input file ID (filename without path or extension)')
correctparser.add_argument('--heuristicSettingsFile', metavar='FILE', type=PathType('r') , help='Path to heuristics settings (generated via make_settings command)')
correctparser.add_argument('--memoizedCorrectionsFile', metavar='FILE', type=PathType('rc') , help='Path to memoizations of corrections.')
correctparser.add_argument('--correctionTrackingFile', metavar='FILE', type=PathType('rc') , help='Path to correction tracking.')
correctparser.add_argument('--dehyphenate', action='store_true', help='repair hyphenation')
correctparser.add_argument('--originalPath', metavar='PATH', type=PathType('d'), help='Path to directory of original, uncorrected files')
correctparser.add_argument('--goldTokenPath', metavar='PATH', type=PathType('d'), help='Path to directory containing tokens with added k-best (generated via tokenize command)')
correctparser.add_argument('--correctedPath', metavar='PATH', type=PathType('d'), help='Directory to output corrected files')

correctparser.set_defaults(func=correcter.correct, **configuration)

args = rootparser.parse_args()

logging.basicConfig(
	stream=sys.stdout,
	format='%(asctime)s - %(levelname)8s - %(name)s - %(message)s',
	level=loglevels[args.loglevel],
)
log = logging.getLogger(progname)

log.info(u'Configuration for this invocation:\n{}'.format(pformat(vars(args))))
args.func(args)

exit()

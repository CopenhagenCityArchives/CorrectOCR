#!/usr/bin/env python

import argparse
import configparser
import logging
import os
import sys
from pathlib import Path
from pprint import pformat

import progressbar
from pycountry import languages

from . import progname
from . import commands
from .workspace import Workspace

defaults = """
[configuration]
characterSet = ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz

[workspace]
rootPath = ./
correctedPath = corrected/
goldPath = gold/
originalPath = original/
trainingPath = training/
nheaderlines = 0
language = Danish

[resources]
resourceRootPath = ./resources/
correctionTrackingFile = correction_tracking.json
dictionaryFile = dictionary.txt
hmmParamsFile = hmm_parameters.json
memoizedCorrectionsFile = memoized_corrections.json
multiCharacterErrorFile = multicharacter_errors.json
reportFile = report.txt
heuristicSettingsFile = settings.json

[storage]
type = fs
db_driver = 
db_host =
db_user =
db_password =
db =

[server]
host = 127.0.0.1
auth_endpoint = http://127.0.0.1/auth
auth_header = auth_token
"""

def setup(configfiles, args=sys.argv[1:]):
	loglevels = dict(logging._nameToLevel)
	del loglevels['NOTSET']
	del loglevels['WARN']

	# windows/mobaxterm/py3.6 fix:
	if os.name == 'nt':
		import io
		sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf8')

	progressbar.streams.wrap_stderr()

	config = configparser.RawConfigParser()
	config.optionxform = lambda option: option
	config.read_string(defaults)
	config.read(configfiles, encoding='utf-8')

	##########################################################################################

	workspaceparser = argparse.ArgumentParser()
	workspaceparser.add_argument('--rootPath', metavar='PATH', type=Path, help='Path to root of workspace')
	workspaceparser.add_argument('--originalPath', metavar='PATH', type=Path, help='Path to directory of original, uncorrected docs')
	workspaceparser.add_argument('--goldPath', metavar='PATH', type=Path, help='Path to directory of known correct "gold" docs')
	workspaceparser.add_argument('--trainingPath', metavar='PATH', type=Path, help='Path for generated training files')
	workspaceparser.add_argument('--correctedPath', metavar='PATH', type=Path, help='Directory to output corrected docs')
	workspaceparser.add_argument('--nheaderlines', metavar='N', type=int, default=0, help='Number of lines in corpus headers (default: 0)')
	workspaceparser.add_argument('--language', type=lambda x: languages.get(name=x), help='Language of text')
	workspaceparser.set_defaults(**dict(config.items('workspace')))
	(workspaceconfig, args) = workspaceparser.parse_known_args(args)
	#print(workspaceconfig, args)

	resourceparser = argparse.ArgumentParser()
	resourceparser.add_argument('--resourceRootPath', metavar='PATH', type=Path, help='Path to root of resources')
	resourceparser.add_argument('--hmmParamsFile', metavar='FILE', type=Path, help='Path to HMM parameters (generated from alignment docs via build_model command)')
	resourceparser.add_argument('--reportFile', metavar='FILE', type=Path, help='Path to output heuristics report (TXT file)')
	resourceparser.add_argument('--heuristicSettingsFile', metavar='FILE', type=Path, help='Path to heuristics settings (generated via make_settings command)')
	resourceparser.add_argument('--multiCharacterErrorFile', metavar='FILE', type=Path, help='Path to output multi-character error file (JSON format)')
	resourceparser.add_argument('--memoizedCorrectionsFile', metavar='FILE', type=Path, help='Path to memoizations of corrections.')
	resourceparser.add_argument('--correctionTrackingFile', metavar='FILE', type=Path, help='Path to correction tracking.')
	resourceparser.add_argument('--dictionaryFile', metavar='FILE', type=Path, help='Path to dictionary file')
	resourceparser.add_argument('--caseInsensitive', action='store_true', default=False, help='Use case insensitive dictionary comparisons')
	resourceparser.set_defaults(**dict(config.items('resources')))
	(resourceconfig, args) = resourceparser.parse_known_args(args)
	#print(resourceconfig, args)

	storageparser = argparse.ArgumentParser()
	storageparser.add_argument('--type', type=str, choices=['db', 'fs'], help='Storage type')
	storageparser.add_argument('--db_driver', type=str, help='Database hostname')
	storageparser.add_argument('--db_host', type=str, help='Database hostname')
	storageparser.add_argument('--db_user', type=str, help='Database username')
	storageparser.add_argument('--db_password', type=str, help='Database user password')
	storageparser.add_argument('--db', type=str, help='Database name')
	storageparser.set_defaults(**dict(config.items('storage')))
	(storageconfig, args) = storageparser.parse_known_args(args)
	storageconfig.trainingPath = workspaceconfig.trainingPath
	#print(storageconfig, args)

	configuration = dict(config.items('configuration'))
	#print(configuration)

	##########################################################################################

	rootparser = argparse.ArgumentParser(prog=progname, description='Correct OCR')

	commonparser = argparse.ArgumentParser(add_help=False)
	commonparser.add_argument('-k', type=int, default=4, help='Number of k-best candidates to use for tokens (default: 4)')
	commonparser.add_argument('--force', action='store_true', default=False, help='Force command to run')
	commonparser.add_argument('--loglevel', type=str, help='Log level', choices=loglevels.keys(), default='INFO')

	subparsers = rootparser.add_subparsers(dest='command', help='Choose command', required=True)

	dictparser = subparsers.add_parser('build_dictionary', parents=[commonparser], help='Build dictionary')
	dictparser.add_argument('--corpusPath', type=Path, default='__COCRcache__/dictionary/', help='Directory of files to split into words and add to dictionary (TXT or PDF format)')
	dictparser.add_argument('--corpusFile', type=Path, help='File containing list URLs to download and use as corpus (TXT format)')
	dictparser.add_argument('--clear', action='store_true', default=False, help='Clear the dictionary before adding words')
	dictparser.set_defaults(func=commands.build_dictionary, **configuration)

	alignparser = subparsers.add_parser('align', parents=[commonparser], help='Create alignments')
	group = alignparser.add_mutually_exclusive_group(required=True)
	group.add_argument('--docid', help='Input document ID (filename without path or extension)')
	group.add_argument('--all', action='store_true', help='Align all original/gold pairs')
	alignparser.add_argument('--exclude', action='append', default=[], help='File ID to exclude (can be specified multiple times)')
	alignparser.set_defaults(func=commands.do_align, **configuration)

	modelparser = subparsers.add_parser('build_model', parents=[commonparser], help='Build model')
	modelparser.add_argument('--smoothingParameter', default=0.0001, metavar='N[.N]', help='Smoothing parameters for HMM (default: 0.0001)')
	modelparser.set_defaults(func=commands.build_model, **configuration)

	prepareparser = subparsers.add_parser('prepare', parents=[commonparser], help='Prepare text for correction')
	group = prepareparser.add_mutually_exclusive_group(required=True)
	group.add_argument('--docid', help='Input document ID (filename without path or extension)')
	group.add_argument('--all', action='store_true', help='Prepare all original/gold pairs')
	prepareparser.add_argument('--exclude', action='append', default=[], help='File ID to exclude (can be specified multiple times)')
	prepareparser.add_argument('--dehyphenate', action='store_true', help='Repair hyphenation')
	prepareparser.add_argument('--step', choices=['tokenize', 'align', 'kbest', 'bin', 'all'], default='all', help='')
	prepareparser.set_defaults(func=commands.do_prepare, **configuration)

	statsparser = subparsers.add_parser('stats', parents=[commonparser], help='Calculate stats for correction decisions')
	group = statsparser.add_mutually_exclusive_group(required=True)
	group.add_argument('--make_report', action='store_true', help='Make heuristics statistics report from tokens')
	group.add_argument('--make_settings', action='store_true', help='Make heuristics settings from report')
	statsparser.set_defaults(func=commands.do_stats, **configuration)

	correctparser = subparsers.add_parser('correct', parents=[commonparser], help='Apply corrections')
	group1 = correctparser.add_mutually_exclusive_group(required=True)
	group1.add_argument('--docid', help='Input document ID (filename without path or extension)')
	group1.add_argument('--filePath', type=Path, help='Input file path (will be copied to originalPath directory)')
	group2 = correctparser.add_mutually_exclusive_group(required=True)
	group2.add_argument('--interactive', action='store_true', default=False, help='Use interactive shell to input and approve suggested corrections')
	group2.add_argument('--apply', type=Path, help='Apply externally corrected token CSV to original document')
	group2.add_argument('--autocorrect', action='store_true', help='Apply automatic corrections as configured in settings')
	correctparser.set_defaults(func=commands.do_correct, **configuration)

	indexparser = subparsers.add_parser('index', parents=[commonparser], help='Generate index data')
	group = indexparser.add_mutually_exclusive_group(required=True)
	group.add_argument('--docid', help='Input document ID (filename without path or extension)')
	group.add_argument('--filePath', type=Path, help='Input file path (will be copied to originalPath directory)')
	indexparser.add_argument('--exclude', action='append', default=[], help='File ID to exclude (can be specified multiple times)')
	indexparser.add_argument('--termFile', type=Path, action='append', default=[], dest='termFiles', required=True, help='File containing a string on each line, which will be matched against the tokens')
	indexparser.add_argument('--highlight', action='store_true', help='Create a copy with highlighted words (only available for PDFs)')
	indexparser.add_argument('--autocorrect', action='store_true', help='Apply automatic corrections as configured in settings')
	indexparser.set_defaults(func=commands.do_index, **configuration)

	cleanupparser = subparsers.add_parser('cleanup', parents=[commonparser], help='Clean up intermediate files')
	cleanupparser.add_argument('--dryrun', action='store_true', help='Don''t delete files, just list them')
	cleanupparser.add_argument('--full', action='store_true', help='Also delete the most recent files (without .nnn. in suffix)')
	cleanupparser.set_defaults(func=commands.do_cleanup, **configuration)

	extractparser = subparsers.add_parser('extract', parents=[commonparser], help='Various extraction methods')
	extractparser.add_argument('--docid', help='Input document ID (filename without path or extension)')
	extractparser.set_defaults(func=commands.do_extract, **configuration)

	serverparser = subparsers.add_parser('server', parents=[commonparser], help='Run JSON-dispensing server')
	serverparser.add_argument('--host', help='The host address')
	serverparser.add_argument('--auth_endpoint', help='Authentication endpoint')
	serverparser.add_argument('--auth_header', help='Authentication header field')
	serverparser.set_defaults(func=commands.run_server, **dict(config.items('server')))

	args = rootparser.parse_args(args)

	workspace = Workspace(workspaceconfig, resourceconfig, storageconfig)

	logging.basicConfig(
		stream=sys.stdout,
		format='%(asctime)s - %(levelname)8s - %(name)s - %(message)s',
		level=loglevels[args.loglevel],
	)
	log = logging.getLogger(progname)

	log.info(f'Configuration for this invocation:\n{pformat(vars(args))}')

	return workspace, args

##########################################################################################

if __name__ == "__main__":
	ws, a = setup(['CorrectOCR.ini'])

	a.func(ws, a)

	exit()

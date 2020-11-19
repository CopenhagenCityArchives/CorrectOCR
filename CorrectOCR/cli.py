import argparse
import logging

from pathlib import Path

from pycountry import languages

from . import progname
from . import commands

loglevels = dict(logging._nameToLevel)
del loglevels['NOTSET']
del loglevels['WARN']


def str2bool(v):
	if isinstance(v, bool):
		return v
	if v.lower() in ('yes', 'true', 't', 'y', '1'):
		return True
	elif v.lower() in ('no', 'false', 'f', 'n', '0'):
		return False
	else:
		raise argparse.ArgumentTypeError('Boolean value expected.')


def get_workspace_argparser():
	workspaceparser = argparse.ArgumentParser()
	
	workspaceparser.add_argument('--rootPath', metavar='PATH', type=Path, help='Path to root of workspace')
	workspaceparser.add_argument('--originalPath', metavar='PATH', type=Path, help='Path to directory of original, uncorrected docs')
	workspaceparser.add_argument('--goldPath', metavar='PATH', type=Path, help='Path to directory of known correct "gold" docs')
	workspaceparser.add_argument('--trainingPath', metavar='PATH', type=Path, help='Path for generated training files')
	workspaceparser.add_argument('--docInfoBaseURL', metavar='URL', type=str, help='Base URL that serves info about documents')
	workspaceparser.add_argument('--nheaderlines', metavar='N', type=int, default=0, help='Number of lines in corpus headers')
	workspaceparser.add_argument('--language', type=lambda x: languages.get(name=x), help='Language of text')

	return workspaceparser

def get_resource_argparser():
	resourceparser = argparse.ArgumentParser()
	
	resourceparser.add_argument('--resourceRootPath', metavar='PATH', type=Path, help='Path to root of resources')
	resourceparser.add_argument('--hmmParamsFile', metavar='FILE', type=Path, help='Path to HMM parameters (generated from alignment docs via build_model command)')
	resourceparser.add_argument('--reportFile', metavar='FILE', type=Path, help='Path to output heuristics report (TXT file)')
	resourceparser.add_argument('--heuristicSettingsFile', metavar='FILE', type=Path, help='Path to heuristics settings (generated via make_settings command)')
	resourceparser.add_argument('--multiCharacterErrorFile', metavar='FILE', type=Path, help='Path to output multi-character error file (JSON format)')
	resourceparser.add_argument('--memoizedCorrectionsFile', metavar='FILE', type=Path, help='Path to memoizations of corrections.')
	resourceparser.add_argument('--correctionTrackingFile', metavar='FILE', type=Path, help='Path to correction tracking.')
	resourceparser.add_argument('--dictionaryFile', metavar='FILE', type=Path, help='Path to dictionary file')
	resourceparser.add_argument('--ignoreCase', action='store_true', default=False, help='Use case insensitive dictionary comparisons')

	return resourceparser

def get_storage_argparser():
	storageparser = argparse.ArgumentParser()

	storageparser.add_argument('--type', type=str, choices=['db', 'fs'], help='Storage type')
	storageparser.add_argument('--db_driver', type=str, help='Database hostname')
	storageparser.add_argument('--db_host', type=str, help='Database hostname')
	storageparser.add_argument('--db_user', type=str, help='Database username')
	storageparser.add_argument('--db_password', type=str, help='Database user password')
	storageparser.add_argument('--db', type=str, help='Database name')

	return storageparser

def get_root_argparser(defaults = None, serverdefaults = None):
	if defaults is None:
		defaults = dict()
	if serverdefaults is None:
		serverdefaults = dict()

	rootparser = argparse.ArgumentParser(prog=progname, description='Correct OCR')

	rootparser.add_argument('-k', type=int, default=4, help='Number of k-best candidates to use for tokens (default: 4)')
	rootparser.add_argument('--force', action='store_true', default=False, help='Force command to run')
	rootparser.add_argument('--loglevel', type=str, help='Log level', choices=loglevels.keys(), default='INFO')

	subparsers = rootparser.add_subparsers(dest='command', help='Choose command')

	dictparser = subparsers.add_parser('build_dictionary', help="""
		Build dictionary.
		
		Input files can be either ``.pdf``, ``.txt``, or ``.xml`` (in `TEI format <https://en.wikipedia.org/wiki/Text_Encoding_Initiative>`__). They may be
		contained in ``.zip``-files.
		
		A ``corpusFile`` for 1800--1948 Danish is available in the ``workspace/resources/``
		directory.
		
		It is strongly recommended to generate a large dictionary for best performance.
		
		.. See :py:mod:`Dictionary<CorrectOCR.dictionary>` for further details.

		See CorrectOCR.dictionary for further details.
	""")
	dictparser.add_argument('--corpusPath', type=Path, default='dictionary/', help='Directory of files to split into words and add to dictionary')
	dictparser.add_argument('--corpusFile', type=Path, help='File containing paths and URLs to use as corpus (TXT format)')
	dictparser.add_argument('--clear', action='store_true', default=False, help='Clear the dictionary before adding words')
	dictparser.set_defaults(func=commands.build_dictionary, **defaults)

	alignparser = subparsers.add_parser('align', help="""
		Create alignments.

		The tokens of each pair of (original, gold) files  are aligned in order to
		determine which characters and words were misread in the original and
		corrected in the gold.
		
		These alignments can be used to train the model.
		
		.. See :py:mod:`Aligner<CorrectOCR.aligner>` for further details.
		
		See CorrectOCR.aligner for further details.
	""")
	group = alignparser.add_mutually_exclusive_group(required=True)
	group.add_argument('--docid', help='Input document ID (filename without path or extension)')
	group.add_argument('--all', action='store_true', help='Align all original/gold pairs')
	alignparser.add_argument('--exclude', action='append', default=[], help='Doc ID to exclude (can be specified multiple times)')
	alignparser.set_defaults(func=commands.do_align, **defaults)

	modelparser = subparsers.add_parser('build_model', help="""
		Build model.
		
		This is done with the aligned original/gold-documents. If none exist, an attempt
		will be made to create them.
		
		The result is an HMM as described in the original paper.
		
		.. See :py:mod:`Model<CorrectOCR.model>` for further details.
		
		See CorrectOCR.model for further details.
	""")
	modelparser.add_argument('--smoothingParameter', default=0.0001, metavar='N[.N]', help='Smoothing parameters for HMM')
	modelparser.set_defaults(func=commands.build_model, **defaults)

	addparser = subparsers.add_parser('add', help="""
		Add documents for processing
		
		One may add a single document directly on the command line, or provide
		a text file containing a list of documents.
		
		They will be copied or downloaded to the ``workspace/original/`` folder.
		
		.. See :py:mod:`Workspace<CorrectOCR.workspace>`
		
		See CorrectOCR.workspace.Workspace for further details.
	""")
	group = addparser.add_mutually_exclusive_group(required=True)
	group.add_argument('document', type=Path, nargs='?', help='Single path/URL to document')
	group.add_argument('--documentsFile', type=Path, help='File containing list of files/URLS to documents')
	addparser.add_argument('--prepare_step', choices=['tokenize', 'align', 'kbest', 'bin', 'all', 'server'], help='Automatically prepare added documents')
	addparser.add_argument('--max_count', type=int, help='Maximum number of new documents to add from --documentsFile.')
	addparser.set_defaults(func=commands.do_add, **defaults)

	prepareparser = subparsers.add_parser('prepare', help="""
		Prepare text for correction.

		.. See :py:class:`Document<CorrectOCR.workspace.Document>`

		See CorrectOCR.workspace.Document
		for further details on the possible steps.
	""")
	group = prepareparser.add_mutually_exclusive_group(required=True)
	group.add_argument('--docid', help='Input document ID (filename without path or extension)')
	group.add_argument('--all', action='store_true', help='Prepare all original/gold pairs')
	prepareparser.add_argument('--exclude', action='append', default=[], help='Doc ID to exclude (can be specified multiple times)')
	prepareparser.add_argument('--dehyphenate', type=str2bool, nargs='?', default=True, help='Automatically mark tokens as hyphenated if they end with a dash')
	prepareparser.add_argument('--step', choices=['tokenize', 'align', 'kbest', 'bin', 'all', 'server'], default='all', help='')
	prepareparser.add_argument('--autocrop', action='store_true', help='Discard tokens near page edges')
	prepareparser.add_argument('--precache_images', action='store_true', help='Create images for the server API')
	prepareparser.set_defaults(func=commands.do_prepare, **defaults)

	cropparser = subparsers.add_parser('crop', help="""
		Mark tokens near the edges of a page as disabled.
		
		This may be desirable for scanned documents where the OCR has picked up
		partial words or sentences near the page edges.
		
		The tokens are not discarded, merely marked disabled so they don't
		show up in the correction interface or generated gold files.
		
		If neither --edge_left nor --edge_right are provided, an attempt
		will be made to calculate them automatically.
	""")
	group = cropparser.add_mutually_exclusive_group(required=True)
	group.add_argument('--docid', help='Input document ID (filename without path or extension)')
	group.add_argument('--all', action='store_true', help='Prepare all original/gold pairs')
	cropparser.add_argument('--edge_left', type=int, help='Set left cropping edge (in pixels)')
	cropparser.add_argument('--edge_right', type=int, help='Set right cropping edge (in pixels)')
	cropparser.set_defaults(func=commands.do_crop, **defaults)

	statsparser = subparsers.add_parser('stats', help="""
		Calculate stats for correction decisions.
		
		The procedure is to first generate a report that shows how many tokens
		have been sorted into each bin. This report can then be annotated with
		the desired decision for each bin, and use this annotated report to
		generate settings for the heuristics.
		
		.. See :py:mod:`Heuristics<CorrectOCR.heuristics>` for further details.

		See CorrectOCR.heuristics.Heuristics for further details.
	""")
	group = statsparser.add_mutually_exclusive_group(required=True)
	group.add_argument('--make_report', action='store_true', help='Make heuristics statistics report from tokens')
	group.add_argument('--make_settings', action='store_true', help='Make heuristics settings from report')
	statsparser.set_defaults(func=commands.do_stats, **defaults)

	correctparser = subparsers.add_parser('correct', help='Apply corrections')
	group1 = correctparser.add_mutually_exclusive_group(required=True)
	group1.add_argument('--docid', help='Input document ID (filename without path or extension)')
	group1.add_argument('--filePath', type=Path, help='Input file path (will be copied to originalPath directory)')
	group2 = correctparser.add_mutually_exclusive_group(required=True)
	group2.add_argument('--interactive', action='store_true', default=False, help='Use interactive shell to input and approve suggested corrections')
	group2.add_argument('--apply', type=Path, help='Apply externally corrected token CSV to original document')
	group2.add_argument('--autocorrect', action='store_true', help='Apply automatic corrections as configured in settings')
	correctparser.add_argument('--highlight', action='store_true', help='Create a copy with highlighted words (only available for PDFs)')
	correctparser.set_defaults(func=commands.do_correct, **defaults)

	goldparser = subparsers.add_parser('make_gold', help='Make gold documents from all ready (fully annotated)')
	goldparser.set_defaults(func=commands.make_gold, **defaults)

	indexparser = subparsers.add_parser('index', help='Generate index data')
	group = indexparser.add_mutually_exclusive_group(required=True)
	group.add_argument('--docid', help='Input document ID (filename without path or extension)')
	group.add_argument('--filePath', type=Path, help='Input file path (will be copied to originalPath directory)')
	indexparser.add_argument('--exclude', action='append', default=[], help='Doc ID to exclude (can be specified multiple times)')
	indexparser.add_argument('--termFile', type=Path, action='append', default=[], dest='termFiles', required=True, help='File containing a string on each line, which will be matched against the tokens')
	indexparser.add_argument('--highlight', action='store_true', help='Create a copy with highlighted words (only available for PDFs)')
	indexparser.add_argument('--autocorrect', action='store_true', help='Apply automatic corrections as configured in settings')
	indexparser.set_defaults(func=commands.do_index, **defaults)

	cleanupparser = subparsers.add_parser('cleanup', help='Clean up intermediate files')
	cleanupparser.add_argument('--dryrun', action='store_true', help='Don''t delete files, just list them')
	cleanupparser.add_argument('--full', action='store_true', help='Also delete the most recent files (without .nnn. in suffix)')
	cleanupparser.set_defaults(func=commands.do_cleanup, **defaults)

	extractparser = subparsers.add_parser('extract', help='Various extraction methods')
	extractparser.add_argument('--docid', help='Input document ID (filename without path or extension)', required=True)
	extractparser.set_defaults(func=commands.do_extract, **defaults)

	serverparser = subparsers.add_parser('server', help='Run basic JSON-dispensing Flask server')
	serverparser.add_argument('--host', help='The host address')
	serverparser.add_argument('--debug', action='store_true', help='Runs the server in debug mode (see Flask docs)')
	serverparser.set_defaults(func=commands.run_server, **serverdefaults)

	return rootparser


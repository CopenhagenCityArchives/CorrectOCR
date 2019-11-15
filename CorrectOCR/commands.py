import collections
import logging
import random
import string
import time
import zipfile
from pathlib import Path
from typing import Dict, List, NamedTuple, Set

import fitz
import progressbar
import requests
from lxml import etree
from tei_reader import TeiReader

from . import progname
from .correcter import CorrectionShell
from .fileio import _open_for_reading, FileIO
from .model import HMMBuilder
from .server import create_app
from .tokens import tokenize_str, Token, Tokenizer
from .workspace import Workspace


##########################################################################################


def build_dictionary(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.build_dictionary')

	if config.clear:
		workspace.resources.dictionary.clear()

	corpusPath = config.corpusPath or FileIO.cachePath('dictionary/')
	FileIO.ensure_directories(corpusPath)

	if config.corpusFile:
		for line in _open_for_reading(config.corpusFile).readlines():
			line = line.strip()
			if len(line) == 0:
				pass
			elif line[0] == '#':
				log.info(line)
			elif line[:4] == 'http':
				if '\t' in line:
					(url, filename) = line.split('\t')
					filename = corpusPath.joinpath(Path(filename).name)
				else:
					url = line
					filename = corpusPath.joinpath(Path(line).name)
				if filename.is_file():
					log.info('Download cached, will not download again.')
					continue
				r = requests.get(url)
				if r.status_code == 200:
					with open(filename, 'wb') as f:
						f.write(r.content)
				else:
					log.error(f'Unable to save file: {r}')
				time.sleep(random.uniform(0.5, 1.5))
			elif line[-1] == '/':
				for file in Path(line).iterdir():
					outfile = corpusPath.joinpath(file.name)
					if outfile.is_file():
						log.info(f'File already copied: {file.name}')
						continue
					log.info(f'Copying {file.name} to corpus.')
					FileIO.copy(file, outfile)

	def unzip_recursive(_zip):
		for member in _zip.namelist():
			if member[-4:] == '.zip':
				log.info(f'Unzipping internal {member}')
				with zipfile.ZipFile(_zip.open(member)) as _zf:
					unzip_recursive(_zf)
			else:
				_zip.extract(member, corpusPath)

	for file in corpusPath.iterdir():
		if file.suffix == '.zip':
			log.info(f'Unzipping {file}')
			with zipfile.ZipFile(file) as zf:
				unzip_recursive(zf)

	ignore: Set[str] = {
		# extraneous files in Joh. V. Jensen zip:
		'teiHeader.xsd',
		'text-format.pdf',
		'text-header.pdf',
		# invalid XML files in Grundtvig zip:
		'1816_297_4_txt.xml',
		'1816_297_7_txt.xml',
		'1816_297_11_txt.xml',
		'1817_306_12_txt.xml',
		'1817_306_13_txt.xml',
		'1817_306_14Txt2Tei.xml',
		'1817_306_15_txt.xml',
		'1817_306_16_txt.xml',
		'1817_309A_txt.xml',
		'1817_310_txt.xml',
		'1818_336A_1_txt.xml',
		'1819_342_1.txt.xml',
		'1819_342_2_txt.xml',
		'1819_342_3_txt.xml',
		'1819_342_txt.xml',
		'1825_410_1_txt.xml',
		'1825_411_1_txt.xml',
		'1826_444_2_txt.xml',
		'1826_444_3_txt.xml',
		'1826_444_4_txt.xml',
		'1826_444_5_txt.xml',
		'1826_450_1_txt.xml',
		'1826_450_2_txt.xml',
		'1826_459_1_txt.xml',
		'1827_456_1_txt.xml',
		'1827_456_2_txt.xml',
		'1827_459_1_txt.xml',
		'1827_459_2_txt.xml',
		'1831_490A_txt.xml',
		'1831_495A_txt.xml',
		'1834_534A_txt.xml',
		'1836_566_txt.xml',
		'1838_601_txt.xml',
		'1839_617_1_txt.xml',
		'1839_617_3.xml',
		'1839_639_txt.xml',
		'1839_641_txt.xml',
		'1840_652_txt.xml',
		'1840_656_txt.xml',
		'1849_946_txt.xml',
		'1849_966_txt.xml',
		'1853_1034_txt.xml',
		'1853_1035_txt.xml',
		'1853_1036_txt.xml',
		'1853_1041.xml',
		'1855_1123_txt.xml',
		'1855_1126a_txt.xml',
		'1855_1126b_txt.xml',
		'1855_1126c_txt.xml',
		'1855_1126d_txt.xml',
		'1855_1126e_txt.xml',
		'1855_1126f_txt.xml',
		'1855_1126g_txt.xml',
		'1855_1129_txt.xml',
		'1856_1135_txt.xml',
		'1856_1138_txt.xml',
		'1858_1229_txt.xml',
		'1859_1242_txt.xml',
		'1859_1254_txt.xml',
		'1861_1283.xml',
		'1864_1365_txt.xml',
		'1866_1394_txt.xml',
		'1866_1396_txt.xml',
	}

	for file in corpusPath.glob('**/*'):
		if file.name[0] == '.' or file.name in ignore:
			continue
		log.info(f'Getting words from {file}')
		if file.suffix == '.pdf':
			doc = fitz.open(str(file))

			for page in progressbar.progressbar(doc):
				for word_info in page.getTextWords():
					workspace.resources.dictionary.add(word_info[4])
		elif file.suffix == '.xml':
			try:
				reader = TeiReader()
				corpora = reader.read_file(file)
			except etree.XMLSyntaxError:
				log.error(f'XML error in {file}')
				continue
			# approved = {'corpus', 'document', 'div', 'part', 'p', 'l', 'w'}
			# text = corpora.tostring(lambda e, t: t if e.tag in approved else '')
			# above didn't work. Instead insert extra space, see issue
			# https://github.com/UUDigitalHumanitieslab/tei_reader/issues/6
			text = corpora.tostring(lambda e, t: f'{t} ')
			for word in tokenize_str(text, workspace.language.name):
				workspace.resources.dictionary.add(word)
		elif file.suffix == '.txt':
			with _open_for_reading(file) as f:
				for word in tokenize_str(f.read(), workspace.language.name):
					workspace.resources.dictionary.add(word)
		else:
			log.error(f'Unrecognized filetype:{file}')
		log.info(f'Wordcount {len(workspace.resources.dictionary)}')

	workspace.resources.dictionary.save()


##########################################################################################


def do_align(workspace: Workspace, config):
	if config.fileid:
		workspace.alignments(config.fileid, force=config.force)
	elif config.all:
		for fileid, pathManager in filter(lambda x: x[1].goldFile.is_file() and x[0] not in config.exclude, workspace.paths.items()):
			workspace.alignments(fileid, force=config.force)


##########################################################################################


def build_model(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.build_model')
	
	# Extra config
	remove_chars: List[str] = [' ', '\t', '\n', '\r', u'\ufeff', '\x00']

	# Select the gold files which correspond to the read count files.
	readCounts = collections.defaultdict(collections.Counter)
	gold_words = []
	for fileid, tokens in workspace.goldTokens():
		(_, _, counts) = workspace.alignments(fileid)
		readCounts.update(counts)
		gold_words.extend([t.gold for t in tokens])
		log.debug(f'{fileid}: {gold_words[-1]}')

	builder = HMMBuilder(workspace.resources.dictionary, config.smoothingParameter, workspace.language, config.characterSet, readCounts, remove_chars, gold_words)

	workspace.resources.hmm.init = builder.init
	workspace.resources.hmm.tran = builder.tran
	workspace.resources.hmm.emis = builder.emis
	workspace.resources.hmm.save()
	

##########################################################################################


def do_prepare(workspace: Workspace, config):
	methods = {
		'tokenize': workspace.tokens,
		'align': workspace.alignedTokens,
		'kbest': workspace.kbestTokens,
		'bin': workspace.binnedTokens,
		'all': workspace.binnedTokens,
	}
	method = methods[config.step]
	Workspace.log.debug(f'Selecting {method} for {config.step}')
	if config.fileid:
		method(fileid=config.fileid, k=config.k, dehyphenate=config.dehyphenate, force=config.force)
	elif config.all:
		for fileid, pathManager in filter(lambda x: x[1].originalFile.is_file() and x[0] not in config.exclude, workspace.paths.items()):
			method(fileid=fileid, k=config.k, dehyphenate=config.dehyphenate, force=config.force)


##########################################################################################


def do_stats(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.do_stats')

	if config.make_report:
		for fileid, goldTokens in workspace.goldTokens():
			log.info(f'Collecting stats from {fileid}')
			for t in goldTokens:
				workspace.resources.heuristics.add_to_report(t)

		log.info(f'Saving report to {workspace.resources.reportFile}')
		FileIO.save(workspace.resources.heuristics.report(), workspace.resources.reportFile)
	elif config.make_settings:
		log.info(f'Reading report from {workspace.resources.reportFile.name}')
		bins = [ln for ln in FileIO.load(workspace.resources.reportFile).split('\n') if "BIN" in ln]
	
		log.info(f'Saving settings to {workspace.resources.heuristicSettingsFile.name}')
		for b in bins:
			binID = b.split()[1]
			action = b.split()[-1]
			workspace.resources.heuristicSettingsFile.write(binID + u'\t' + action + u'\n')


##########################################################################################


def do_correct(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.do_correct')

	if config.filePath:
		fileid = config.filePath.stem
		if fileid in workspace.paths:
			log.error(f'File ID already exists: {fileid}! You must rename the file first.')
			raise SystemExit(-1)
		workspace.add_fileid(fileid, config.filePath.suffix, new_original=config.filePath)
	else:
		fileid = config.fileid
	
	if config.autocorrect:
		log.info(f'Getting autocorrected tokens')
		corrected = workspace.autocorrectedTokens(config.fileid, k=config.k)
	elif config.apply:
		log.info(f'Getting corrections from {config.apply}')
		if not config.apply.is_file():
			log.error(f'Unable to apply non-file path {config.apply}')
			raise SystemExit(-1)
		corrected = [Token.from_dict(row) for row in FileIO.load(config.apply)]
	elif config.interactive:
		log.info(f'Getting corrections from interactive session')
		binned_tokens = workspace.binnedTokens(config.fileid, k=config.k)

		# get header, if any
		#header = workspace.paths[fileid].correctedFile.header
		# print info to annotator
		#log.info(f'header: {header}')

		metrics = CorrectionShell.start(binned_tokens, workspace.resources.dictionary, workspace.resources.correctionTracking)
		corrected = binned_tokens
		log.debug(metrics['newWords'])
		log.debug(metrics['correctionTracking'])

		if metrics:
			log.info(f'Saving metrics.')
			for key, count in sorted(metrics['correctionTracking'].items(), key=lambda x: x[1], reverse=True):
				(original, gold) = key.split('\t')
				workspace.resources.memoizedCorrections[original] = gold
				workspace.resources.correctionTracking[f'{original}\t{gold}'] = count
			workspace.resources.correctionTracking.save()
			workspace.resources.memoizedCorrections.save()
	else:
		log.critical('This shouldn''t happen!')
		raise SystemExit(-1)

	log.info(f'Applying corrections to {fileid}')
	Tokenizer.for_extension(workspace.paths[fileid].ext).apply(
		workspace.paths[fileid].originalFile,
		corrected,
		workspace.paths[fileid].correctedFile,
	)


##########################################################################################


def do_index(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.do_index')

	outfile = Path('index.csv')

	taggedTerms: Dict[str, List[str]] = dict()
	for termFile in config.termFiles:
		taggedTerms[termFile.stem] = []
		for line in FileIO.load(termFile).split('\n'):
			term = line.lower().lstrip(string.punctuation).rstrip(string.punctuation).strip()
			taggedTerms[termFile.stem].append(term)

	log.debug(f'terms: {[(t, len(c)) for t, c in taggedTerms.items()]}')

	class TaggedToken(NamedTuple):
		token: Token
		tags: List[str]

	def match_terms(fileid: str) -> List[List[TaggedToken]]:
		log.info(f'Finding matching terms for {fileid}')

		if config.autocorrect:
			log.info(f'Getting autocorrected tokens')

			tokens = workspace.autocorrectedTokens(fileid, k=config.k)
		else:
			log.info(f'Getting unprepared tokens')

			tokens = workspace.tokens(fileid)

		log.info(f'Searching for terms')
		matches = []
		run = []
		for token in progressbar.progressbar(tokens):
			tt = TaggedToken(token, [])
			matched = False
			for tag, terms in taggedTerms.items():
				key = token.gold if token.gold and token.gold != '' else token.normalized
				key = key.lstrip(string.punctuation).rstrip(string.punctuation)
				log.debug(f'token: {token} key: {key}')
				if key != '' and key.lower() in terms:
					tt.tags.append(tag)
					matched = True
			if len(tt.tags) > 0:
				run.append(tt)
			if not matched:
				# TODO require all of a kind? names.given + names.surname?
				if len(run) > 1:
					#log.debug(f'Adding run: {run}')
					matches.append(run)
				run = []

		if config.highlight and workspace.paths[fileid].ext == '.pdf':
			from .tokens._pdf import PDFToken
			log.info(f'Applying highlights')
			pdf = fitz.open(workspace.paths[fileid].originalFile)
			red = (1.0, 0.0, 0.0)
			for run in matches:
				for tagged_token in run:
					token: PDFToken = tagged_token.token
					page = pdf[token.ordering[0]]
					annotation = page.addRectAnnot(token.rect)
					annotation.setColors({'fill': red, 'stroke': red})
					annotation.setOpacity(0.5)
					annotation.info['title'] = progname
					annotation.info['content'] = str.join(', ', tagged_token.tags)
					annotation.update()
			filename = f'{fileid}-highlighted.pdf'
			log.info(f'Saving highlighted PDF to {filename}')
			pdf.save(filename)

		return matches
	
	matches = dict()
	if config.fileid:
		matches[config.fileid] = match_terms(fileid=config.fileid)
	elif config.all:
		matches = dict()
		for fileid, pathManager in filter(lambda x: x[1].originalFile.is_file() and x[0] not in config.exclude, workspace.paths.items()):
			matches[fileid] = match_terms(fileid=fileid)
	#log.debug(f'matches: {matches}')

	rows = []
	for fileid, runs in matches.items():
		for run in runs:
			#log.debug(f'run: {run}')
			for tagged_tokens in run:
				rows.append({
					'fileid': fileid,
					'tokens': [r.token.normalized for r in run],
					'tags': [r.tags for r in run],
				})
	if len(rows) > 0:
		log.info(f'Saving index to {outfile}')
		FileIO.save(rows, outfile)


##########################################################################################


def do_cleanup(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.do_cleanup')

	workspace.cleanup(config.dryrun, config.full)


##########################################################################################


def do_extract(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.do_extract')

	tokens = [t for t in workspace.binnedTokens(config.fileid) if t.decision == 'annotator']

	for token in progressbar.progressbar(tokens):
		(filename, image) = token.extract_image(workspace)


##########################################################################################


def run_server(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.run_server')

	app = create_app(workspace, config)
	app.run()

import collections
import hashlib
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
from .model.hmm import HMMBuilder
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

	def md5(data):
		return hashlib.md5(str(data).encode('utf-8')).hexdigest()

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
					filename = corpusPath.joinpath(md5(url)).joinpath(Path(filename).name)
				else:
					url = line
					filename = corpusPath.joinpath(md5(url)).joinpath(Path(line).name)
				if filename.is_file():
					log.info('Download cached, will not download again.')
					continue
				r = requests.get(url)
				if r.status_code == 200:
					FileIO.ensure_directories(filename.parent)
					with open(filename, 'wb') as f:
						f.write(r.content)
				else:
					log.error(f'Unable to save file: {r}')
				time.sleep(random.uniform(0.5, 1.5))
			elif line[-1] == '/':
				for file in Path(line).iterdir():
					outfile = corpusPath.joinpath(md5(line)).joinpath(file.name)
					if outfile.is_file():
						log.info(f'File already copied: {file.name}')
						continue
					log.info(f'Copying {file.name} to corpus.')
					FileIO.copy(file, outfile)

	# TODO use ame destination for all contents of top level zip?
	def unzip_recursive(_zip):
		destination = corpusPath.joinpath(md5(_zip))
		if destination.is_dir():
			log.debug(f'Already unzipped, skipping: {_zip}')
			return
		for member in _zip.namelist():
			if member[-4:] == '.zip':
				log.debug(f'Unzipping internal {member}')
				with zipfile.ZipFile(_zip.open(member)) as _zf:
					unzip_recursive(_zf)
			else:
				_zip.extract(member, destination)

	for file in corpusPath.rglob('*.zip'):
		log.info(f'Unzipping {file}')
		with zipfile.ZipFile(file) as zf:
			unzip_recursive(zf)

	ignore: Set[str] = {
		# extraneous files in Joh. V. Jensen zip:
		'teiHeader.xsd',
		'text-format.pdf',
		'text-header.pdf',
		# extraneous files in Grundtvig zip:
		'1817_9.xml', # in German
	}

	existing_groups = set(workspace.resources.dictionary.groups.keys())
	for group_path in corpusPath.iterdir():
		log.info(f'Checking corpus {group_path}')
		group = group_path.stem
		if group in existing_groups:
			log.info(f'Skipping {group}, it is already in dictionary')
			continue
		for file in group_path.rglob('*.*'):
			if file.name[0] == '.' or file.name in ignore:
				continue
			log.info(f'Getting words from {file.resolve()}')
			if file.suffix == '.pdf':
				doc = fitz.open(str(file))

				for page in progressbar.progressbar(doc):
					for word_info in page.getTextWords():
						workspace.resources.dictionary.add(group, word_info[4])
			elif file.suffix == '.xml':
				try:
					reader = TeiReader()
					corpora = reader.read_file(file)
				except etree.XMLSyntaxError:
					log.error(f'XML error in {file}')
					continue
				# TODO broken...
				# approved = {'corpus', 'document', 'div', 'part', 'p', 'l', 'w'}
				# text = corpora.tostring(lambda e, t: t if e.tag in approved else '')
				# above didn't work. Instead insert extra space, see issue
				# https://github.com/UUDigitalHumanitieslab/tei_reader/issues/6
				text = corpora.tostring(lambda e, t: f'{t} ')
				for word in tokenize_str(text, workspace.config.language.name):
					workspace.resources.dictionary.add(group, word)
			elif file.suffix == '.txt':
				with _open_for_reading(file) as f:
					for word in tokenize_str(f.read(), workspace.config.language.name):
						workspace.resources.dictionary.add(group, word)
			else:
				log.error(f'Unrecognized filetype: {file}')
		workspace.resources.dictionary.save_group(group)

	if config.add_annotator_gold:
		for docid in workspace.docids_for_ext('.pdf', is_done=True):
			group = f'gold-{docid}'
			if group in existing_groups:
				log.info(f'Skipping {group}, it is already in dictionary')
				continue
			doc = workspace.docs[docid]
			if not doc.tokens.stats['done']:
				log.info(f'Skipping {docid}, it is not done')
				continue
			log.info(f'Adding gold words from annotated tokens in document {docid}')
			for original, gold, token in progressbar.progressbar(doc.tokens.consolidated, max_value=len(doc.tokens)):
				#print([token, token.decision, token.gold, token.is_discarded])
				if token.decision == 'annotator' and gold is not None:
					if gold not in workspace.resources.dictionary:
						log.info(f'Adding {gold}')
						workspace.resources.dictionary.add(group, gold)
					else:
						log.debug(f'{gold} is already in dictionary')
			workspace.resources.dictionary.save_group(group)

	workspace.resources.dictionary.save()


##########################################################################################


def do_align(workspace: Workspace, config):
	if config.docid:
		workspace.docs[config.docid].alignments(force=config.force)
	elif config.all:
		for docid, doc in filter(lambda x: x[1].goldFile.is_file() and x[0] not in config.exclude, workspace.docs.items()):
			doc.alignments(force=config.force)


##########################################################################################


def build_model(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.build_model')
	
	# Extra config
	remove_chars: List[str] = [' ', '\t', '\n', '\r', u'\ufeff', '\x00']

	# Select the gold docs which correspond to the read count files.
	readCounts = collections.defaultdict(collections.Counter)
	gold_words = []
	for docid in workspace.docids_for_ext('.pdf', is_done=True):
		doc = workspace.docs[docid]
		(_, _, counts) = doc.alignments
		readCounts.update(counts)
		for original, gold, token in progressbar.progressbar(doc.tokens.consolidated, max_value=len(doc.tokens)):
			gold_words.append(gold)

	builder = HMMBuilder(workspace.resources.dictionary, config.smoothingParameter, config.characterSet, readCounts, remove_chars, gold_words)

	workspace.resources.hmm.init = builder.init
	workspace.resources.hmm.tran = builder.tran
	workspace.resources.hmm.emis = builder.emis
	workspace.resources.hmm.save()
	

##########################################################################################


def do_add(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.do_add')

	if config.document:
		files = [config.document]
	else:
		files = []
		for line in _open_for_reading(config.documentsFile).readlines():
			line = line.strip()
			if len(line) == 0:
				pass
			elif line[0] == '#':
				log.info(line)
			else:
				if line[:4] == 'http':
					files.append(line) # TODO urllib.parse?
				else:
					files.append(Path(line))

	count = 0

	for file in files:
		log.info(f'Adding {file}')
		doc_id = workspace.add_doc(file)
		if config.prepare_step:
			workspace.docs[doc_id].prepare(config.prepare_step, k=config.k)
		count += 1
		if config.max_count and config.max_count > count:
			break


##########################################################################################


def do_prepare(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.prepare')
	
	if config.docid:
		docs = [(config.docid, workspace.docs[config.docid])]
	elif config.all:
		docs = filter(lambda x: x[1].originalFile.is_file() and x[0] not in config.exclude, workspace.docs.items())
	else:
		docs = []

	for docid, doc in docs:
		doc.prepare(config.step, k=config.k, dehyphenate=config.dehyphenate, force=config.force)
		if config.autocrop:
			doc.crop_tokens()
		if config.precache_images:
			doc.precache_images()


##########################################################################################


def do_crop(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.crop')
	
	if config.docid:
		workspace.docs[config.docid].crop_tokens(config.edge_left, config.edge_right)
	elif config.all:
		for docid, doc in filter(lambda x: x[1].originalFile.is_file() and x[0] not in config.exclude, workspace.docs.items()):
			doc.crop_tokens(config.edge_left, config.edge_right)
			


##########################################################################################


def do_stats(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.do_stats')

	if config.make_report:
		for docid in workspace.docids_for_ext('.pdf', is_done=True):
			log.info(f'Collecting stats from {docid}')
			doc = workspace.docs[docid]
			for original, gold, token in progressbar.progressbar(doc.tokens.consolidated, max_value=len(doc.tokens)):
				workspace.resources.heuristics.add_to_report(token)

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
		docid = workspace.add_doc(config.filePath)
	else:
		docid = config.docid

	doc = workspace.docs[config.docid]

	if config.autocorrect:
		log.info(f'Getting autocorrected tokens')
		doc.prepare('autocorrect', k=config.k)
		corrected = doc.tokens
	elif config.apply:
		log.info(f'Getting corrections from {config.apply}')
		if not config.apply.is_file():
			log.error(f'Unable to apply non-file path {config.apply}')
			raise SystemExit(-1)
		corrected = [Token.from_dict(row) for row in FileIO.load(config.apply)]
	elif config.interactive:
		log.info(f'Getting corrections from interactive session')
		workspace.docs[config.docid].prepare('bin', k=config.k)

		metrics = CorrectionShell.start(doc.tokens, workspace.resources.dictionary, workspace.resources.correctionTracking)
		corrected = workspace.docs[config.docid].tokens
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
	elif config.gold_ready:
		missing_gold_count = 0
		for original, gold, token in progressbar.progressbar(doc.tokens.consolidated, max_value=len(doc.tokens)):
			if not gold:
				missing_gold_count += 1

		if missing_gold_count == 0:
			log.info(f'Document {docid} is fully corrected! Applying corrections in new gold file.')
			corrected = doc.tokens
		else:
			log.info(f'Document {docid} has {missing_gold_count} tokens without gold')
	else:
		log.critical('This shouldn''t happen!')
		raise SystemExit(-1)

	corrected = [t for t in corrected if not t.is_discarded]

	log.info(f'Applying corrections to {docid}')
	Tokenizer.for_extension(doc.ext).apply(
		doc.originalFile,
		corrected,
		doc.goldFile,
		highlight=config.highlight
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

	def match_terms(doc) -> List[List[TaggedToken]]:
		log.info(f'Finding matching terms for {docid}')

		if config.autocorrect:
			log.info(f'Autocorrecting tokens')
			doc.prepare('autocorrect', k=config.k)

		log.info(f'Searching for terms')
		matches = []
		run = []
		for original, gold, token in progressbar.progressbar(doc.tokens.consolidated, max_value=len(doc.tokens)):
			tt = TaggedToken(token, [])
			matched = False
			for tag, terms in taggedTerms.items():
				key = gold if token.gold and gold != '' else token.normalized
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

		if config.highlight and workspace.docs[docid].ext == '.pdf':
			from .tokens._pdf import PDFToken
			log.info(f'Applying highlights')
			pdf = fitz.open(workspace.docs[docid].originalFile)
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
			filename = f'{docid}-highlighted.pdf'
			log.info(f'Saving highlighted PDF to {filename}')
			pdf.save(filename)

		return matches
	
	matches = dict()
	if config.docid:
		matches[config.docid] = match_terms(workspace.docs[config.docid])
	elif config.all:
		matches = dict()
		for docid, doc in filter(lambda x: x[1].originalFile.is_file() and x[0] not in config.exclude, workspace.docs.items()):
			matches[docid] = match_terms(doc)
	#log.debug(f'matches: {matches}')

	rows = []
	for docid, runs in matches.items():
		for run in runs:
			#log.debug(f'run: {run}')
			rows.append({
				'docid': docid,
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


def run_server(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.run_server')

	app = create_app(workspace, config)
	app.run()

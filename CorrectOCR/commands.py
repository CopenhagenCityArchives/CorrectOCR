import collections
import logging
import random
import shutil
import time
import zipfile
from pathlib import Path
from typing import List, Set

import progressbar
import requests
from lxml import etree
from tei_reader import TeiReader

from . import open_for_reading, extract_text_from_pdf, FileAccess
from .correcter import Correcter, CorrectionShell
from .model import HMM, HMMBuilder
from .tokenize import tokenize_str
from .workspace import Workspace


##########################################################################################


def build_dictionary(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.build_dictionary')
	
	if config.corpusFile:
		for line in open_for_reading(config.corpusFile).readlines():
			line = line.strip()
			if len(line) == 0:
				pass
			elif line[0] == '#':
				log.info(line)
			elif line[:4] == 'http':
				if '\t' in line:
					(url, filename) = line.split('\t')
					filename = config.corpusPath.joinpath(Path(filename).name)
				else:
					url = line
					filename = config.corpusPath.joinpath(Path(line).name)
				if filename.exists():
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
					outfile = config.corpusPath.joinpath(file.name)
					if outfile.exists():
						log.info(f'File already copied: {file.name}')
						continue
					log.info(f'Copying {file.name} to corpus.')
					shutil.copy(str(file), outfile)

	def unzip_recursive(_zip):
		for member in _zip.namelist():
			if member[-4:] == '.zip':
				log.info(f'Unzipping internal {member}')
				with zipfile.ZipFile(_zip.open(member)) as _zf:
					unzip_recursive(_zf)
			else:
				_zip.extract(member, config.corpusPath)

	for file in config.corpusPath.iterdir():
		if file.suffix == '.zip':
			log.info(f'Unzipping {file}')
			with zipfile.ZipFile(file) as zf:
				unzip_recursive(zf)

	ignore: Set[str] = {
		'.DS_Store',
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

	for file in config.corpusPath.glob('**/*'):
		if file.name[0] == '.' or file.name in ignore:
			continue
		log.info(f'Getting words from {file}')
		if file.suffix == '.pdf':
			text = extract_text_from_pdf(file)
			for word in tokenize_str(str(text), workspace.language.name):
				workspace.resources.dictionary.add(word)
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
			with open_for_reading(file) as f:
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
	elif config.allPairs:
		for goldFile in workspace.goldFiles():
			workspace.alignments(goldFile.stem, force=config.force)


##########################################################################################


def build_model(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.build_model')
	
	# Extra config
	remove_chars: List[str] = [' ', '\t', '\n', '\r', u'\ufeff', '\x00']

	# Select the gold files which correspond to the misread count files.
	misreadCounts = collections.defaultdict(collections.Counter)
	gold_files = []
	for file in workspace.goldFiles():
		(_, _, counts) = workspace.alignments(file.stem)
		misreadCounts.update(counts)
		gold_files.append(workspace.goldFile(file.stem))
	
	confusion = HMMBuilder.generate_confusion(misreadCounts, remove_chars)
	char_counts = HMMBuilder.text_char_counts(gold_files, workspace.resources.dictionary, remove_chars)

	charset = set(config.characterSet) | set(char_counts) | set(confusion)

	log.debug(sorted(charset))

	# Create the emission probabilities from the misread counts and the character counts
	emis = HMMBuilder.emission_probabilities(confusion, char_counts, config.smoothingParameter, remove_chars,
                               extra_chars=charset)

	# Create the initial and transition probabilities from the gold files
	init, tran = HMMBuilder.init_tran_probabilities(gold_files, workspace.resources.dictionary, config.smoothingParameter,
                                         remove_chars, workspace.language, extra_chars=charset)

	workspace.resources.hmm = HMM(init, tran, emis)
	workspace.resources.hmm.save(workspace.resources.hmmParamsFile) # TODO keep path inside hmm like dicts?
	

##########################################################################################


def do_tokenize(workspace: Workspace, config):
	if config.fileid:
		workspace.tokens(config.fileid, config.k, force=config.force)
	elif config.all:
		for goldFile in workspace.goldFiles():
			workspace.tokens(goldFile.stem, config.k, force=config.force)


##########################################################################################


def make_report(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.make_report')

	for fileid, goldTokens in workspace.goldTokens():
		log.info(f'Collecting stats from {fileid}')
		for t in goldTokens:
			workspace.resources.heuristics.add_to_report(t)
	
	config.reportFile.writelines(workspace.resources.heuristics.report())


def make_settings(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.make_settings')
	
	log.info(f'Reading report from {workspace.resources.reportFile.name}')
	bins = [ln for ln in workspace.resources.reportFile.readlines() if "BIN" in ln]
	
	log.info(f'Writing settings to {workspace.resources.heuristicSettingsFile.name}')
	for b in bins:
		binID = b.split()[1]
		action = b.split()[-1]
		workspace.resources.heuristicSettingsFile.write(binID + u'\t' + action + u'\n')


##########################################################################################


def do_correct(workspace: Workspace, config):
	log = logging.getLogger(f'{__name__}.do_correct')
	
	correcter = Correcter(
		workspace.resources.dictionary,
		workspace.resources.heuristics,
		workspace.resources.memoizedCorrections,
		workspace.resources.dictionary.caseInsensitive,
		config.k
	)
	
	# get tokens to use for correction
	tokens = workspace.tokens(config.fileid)
	
	log.info('Running heuristics on tokens to determine annotator workload.')
	annotatorRequired = 0
	for t in progressbar.progressbar(tokens):
		(t.bin['decision'], t.bin['selection']) = correcter.evaluate(t)
		if t.bin['decision'] == 'annotator':
			annotatorRequired += 1
	log.info(f'Annotator required for {annotatorRequired} of {len(tokens)} tokens.')
	
	path = workspace.binnedTokenFile(config.fileid)
	rows = [t.as_dict() for t in tokens]

	FileAccess.save(rows, path, FileAccess.CSV, header=FileAccess.BINNEDHEADER)

	if not config.interactive:
		return

	# try to combine hyphenated linebreaks before correction
	linecombine = True
	
	log.info(f'Correcting {config.fileid}')
	origfilename = workspace.originalFile(config.fileid)
	
	# get metadata, if any
	if config.nheaderlines > 0:
		with open_for_reading(origfilename) as f:
			metadata = f.readlines()[:config.nheaderlines]
	else:
		metadata = ''

	if linecombine:
		tokens = correcter.linecombiner(tokens)

	# print info to annotator
	log.info(f'{config.fileid} contains about {len(tokens)} words')
	for l in metadata:
		log.info(l)
	
	tracking = CorrectionShell.start(tokens, workspace.resources.dictionary, workspace.resources.correctionTracking)

	#log.debug(tokens)
	log.debug(tracking['newWords'])
	log.debug(tracking['correctionTracking'])

	# optionally clean up hyphenation in completed tokens
	if config.dehyphenate:
		tokens = [correcter.dehyph(tk) for tk in tokens]

	# make print-ready text
	spaced = u' '.join([token.gold or token.original for token in tokens])
	despaced = spaced.replace('_NEWLINE_N_', '\n').replace(' \n ', '\n')

	corrected = metadata.replace(u'Corrected: No', u'Corrected: Yes') + despaced
	
	FileAccess.save(corrected, workspace.correctedFile(config.fileid))
	
	# update tracking & memos of annotator's actions
	for key, count in sorted(tracking['correctionTracking'].items(), key=lambda x: x[1], reverse=True):
		(original, gold) = key.split('\t')
		workspace.resources.memoizedCorrections[original] = gold
		workspace.resources.correctionTracking[f'{original}\t{gold}'] = count
	workspace.resources.correctionTracking.save()
	workspace.resources.memoizedCorrections.save()

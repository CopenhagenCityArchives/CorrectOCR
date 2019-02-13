import collections
import logging
import random
import shutil
import time

import progressbar

from . import ensure_new_file
from .dictionary import Dictionary
from .aligner import Aligner
from .model import HMM, HMMBuilder
from .correcter import Correcter, CorrectionShell
from .tokenize.string import tokenize_string

##########################################################################################


def build_dictionary(workspace, config):
	log = logging.getLogger(f'{__name__}.build_dictionary')
	
	if config.corpusFile:
		for line in config.corpusFile.readlines():
			line = line.strip()
			if len(line) == 0:
				pass
			elif line[0] == '#':
				log.info(line)
			elif line[:4] == 'http':
				outfile = config.corpusPath.joinpath(Path(line).name)
				if outfile.exists():
					log.info('Download cached, will not download again.')
					continue
				r = requests.get(line)
				if r.status_code == 200:
					with open(outfile, 'wb') as f:
						f.write(r.content)
				else:
					log.error(f'Unable to save file: {r}')
				time.sleep(random.uniform(0.5, 1.5))
			elif line[-1] == '/':
				for file in Path(line).iterdir():
					outfile = config.corpusPath.joinpath(Path(line).name)
					if outfile.exists():
						log.info(f'File already copied: {file}')
						continue
					log.info(f'Copying {file} to corpus.')
					shutil.copy(file, outfile)
	
	for file in config.corpusPath.iterdir():
		log.info(f'Getting words from {file}')
		if file.suffix == '.pdf':
			text = extract_text_from_pdf(file)
			for word in tokenize_string(str(text), config.language.name, objectify=False):
				workspace.resources.dictionary.add(word)
		elif file.suffix == '.txt':
			with open_for_reading(file) as f:
				for word in tokenize_string(f.read(), config.language.name, objectify=False):
					workspace.resources.dictionary.add(word)
		else:
			log.error(f'Unrecognized filetype:{file}')
		log.info(f'Wordcount {len(workspace.resources.dictionary)}')

	workspace.resources.dictionary.save()


##########################################################################################


def do_align(workspace, config):
	if config.fileid:
		workspace.alignments(config.fileid, config.language.name, force=config.force)
	elif config.allPairs:
		for goldFile in workspace.goldFiles():
			workspace.alignments(goldFile.stem, config.language.name, force=config.force)


##########################################################################################


def build_model(workspace, config):
	log = logging.getLogger(f'{__name__}.build_model')
	
	# Extra config
	remove_chars = [' ', '\t', '\n', '\r', u'\ufeff', '\x00']

	# Select the gold files which correspond to the misread count files.
	misreadCounts = collections.defaultdict(collections.Counter)
	gold_files = []
	for file in workspace.goldFiles():
		(_, _, counts) = workspace.alignments(file.stem)
		misreadCounts.update(counts)
		gold_files.append(workspace.goldFile(file.stem))
	
	confusion = HMMBuilder.generate_confusion(misreadCounts, remove_chars)
	char_counts = HMMBuilder.text_char_counts(gold_files, workspace.resources.dictionary, remove_chars, config.nheaderlines)

	charset = set(config.characterSet) | set(char_counts) | set(confusion)

	log.debug(sorted(charset))

	# Create the emission probabilities from the misread counts and the character counts
	emis = HMMBuilder.emission_probabilities(confusion, char_counts, config.smoothingParameter, remove_chars,
                               extra_chars=charset)

	# Create the initial and transition probabilities from the gold files
	init, tran = HMMBuilder.init_tran_probabilities(gold_files, workspace.resources.dictionary, config.smoothingParameter,
                                         remove_chars, config.nheaderlines, extra_chars=charset)

	workspace.resources.hmm = HMM(init, tran, emis)
	workspace.resources.hmm.save(workspace.resources.hmmParamsFile) # TODO keep path inside hmm like dicts?
	

##########################################################################################


def do_tokenize(workspace, config, getWordAlignments=True):
	if config.fileid:
		workspace.tokens(config.fileid, config.nheaderlines, config.k, config.language.name, getWordAlignments, force=config.force)
	elif config.all:
		for goldFile in workspace.goldFiles():
			workspace.tokens(goldFile.stem, config.nheaderlines, config.k, config.language.name, getWordAlignments, force=config.force)


##########################################################################################


def make_report(workspace, config):
	log = logging.getLogger(f'{__name__}.make_report')
	
	dictionary = Dictionary(config.dictionaryFile, config.caseInsensitive)
	heuristics = Heuristics(dictionary, config.caseInsensitive, k=config.k)
	
	for goldTokens in workspace.goldTokens():
		log.info(f'Collecting stats from {file}')
		for t in goldTokens:
			heuristics.add_to_report(t)
	
	config.reportFile.writelines(heuristics.report())


def make_settings(workspace, config):
	log = logging.getLogger(f'{__name__}.make_settings')
	
	log.info(f'Reading report from {workspace.resources.reportFile.name}')
	bins = [ln for ln in workspace.resources.reportFile.readlines() if "BIN" in ln]
	
	log.info(f'Writing settings to {workspace.resources.heuristicSettingsFile.name}')
	for b in bins:
		binID = b.split()[1]
		action = b.split()[-1]
		workspace.resources.heuristicSettingsFile.write(binID + u'\t' + action + u'\n')


##########################################################################################


def do_correct(workspace, config):
	log = logging.getLogger(f'{__name__}.do_correct')
	
	correcter = Correcter(
		workspace.resources.dictionary,
		workspace.resources.heuristics,
		workspace.resources.memoizedCorrections,
		workspace.resources.dictionary.caseInsensitive,
		config.k
	)
	
	# get tokens to use for correction
	tokens = workspace.tokens(config.fileid, language=config.language.name, getWordAlignments=False)
	
	log.info('Running heuristics on tokens to determine annotator workload.')
	annotatorRequired = 0
	for t in progressbar.progressbar(tokens):
		(t.bin['decision'], t.bin['selection']) = correcter.evaluate(t)
		annotatorRequired += 1
	log.info(f'Annotator required for {annotatorRequired} of {len(tokens)} tokens.')
	
	path = workspace.binnedTokenFile(config.fileid)
	rows = [t.as_dict() for t in tokens]

	# TODO:
	workspace.__class__.save(rows, path, workspace.__class__.CSV, header=workspace.__class__.BINNEDHEADER)

	if not config.interactive:
		return

	# try to combine hyphenated linebreaks before correction
	linecombine = True
	
	log.info(f'Correcting {config.fileid}')
	origfilename = workspace.originalFile(config.fileid)
	
	correctfilename = ensure_new_file(workspace.correctedFile(config.fileid))
	o = open(correctfilename, 'w', encoding='utf-8')

	# get metadata, if any
	if config.nheaderlines > 0:
		with open_for_reading(origfilename) as f:
			metadata = f.readlines()[:config.nheaderlines]
	else:
		metadata = ''

	# and write it to output file, replacing 'Corrected: No' with 'Yes'
	for l in metadata:
		o.write(l.replace(u'Corrected: No', u'Corrected: Yes'))

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
		tokens = [dehyph(tk) for tk in tokens]

	# make print-ready text
	spaced = u' '.join([token.gold or token.original for token in tokens])
	despaced = spaced.replace('_NEWLINE_N_', '\n').replace(' \n ', '\n')

	# write corrected output
	o.write(despaced)
	o.close()
	
	# update tracking & memos of annotator's actions
	for key, count in sorted(tracking['correctionTracking'].items(), key=lambda x: x[1], reverse=True):
		(original, gold) = key.split('\t')
		workspace.resources.memoizedCorrections[original] = gold
		workspace.resources.correctionTracking[f'{original}\t{gold}'] = count
	workspace.resources.correctionTracking.save()
	workspace.resources.memoizedCorrections.save()

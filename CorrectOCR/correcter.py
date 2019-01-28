# coding=utf-8
# c richter / ricca@seas.upenn.edu
import regex
import cmd
import json
import csv
import logging
import readline
from collections import defaultdict
from pathlib import Path

from . import tokenizer
from . import open_for_reading, splitwindow, ensure_new_file
from .dictionary import Dictionary
from .heuristics import Heuristics

'''
IMPORTANT BEFORE USING:
To display interactive text your environment must be compatible with the encoding.
For example:
> export LANG=is_IS.UTF-8
> export LC_ALL=is_IS.UTF-8
> locale
> export PYTHONIOENCODING=utf8
'''


class Correcter(object):
	def __init__(self, dictionary, heuristicSettingsFile, memos, caseInsensitive=False, k=4):
		self.caseInsensitive = caseInsensitive
		self.memos = memos
		self.k = k
		self.log = logging.getLogger(__name__+'.Correcter')
		self.dictionary = dictionary
		self.heuristics = Heuristics(self.dictionary, self.caseInsensitive, settingsFile=heuristicSettingsFile)
		self.punctuation = regex.compile(r'\p{posix_punct}+')
	
	# remove selected hyphens from inside a single token - postprocessing step
	def dehyph(self, tk):
		o = tk
		# if - in token, and token is not only punctuation, and - is not at end or start of token:
		if (u'-' in tk) & ((len(self.punctuation.sub('', tk)) > 0) & ((tk[-1] != u'-') & (tk[0] != u'-'))):
			# if - doesn't precede capital letter, and the word including dash form isn't in dictionary:
			if ((not tk[tk.index(u'-')+1].isupper()) & ((not tk in dws) & (not tk.lower() in dws))):
				# if the word not including dash form is in dictionary, only then take out the dash
				if ((self.punctuation.sub('', tk) in dws) or (self.punctuation.sub('', tk).lower() in dws)):
					o = tk.replace(u'-', u'')
		return(o)
	
	# try putting together some lines that were split by hyphenation - preprocessing step
	def linecombiner(self, ls):
		for i in range(len(ls) - 2):
			if (ls[i] != u'BLANK'):
				#self.log.debug(ls[i])
				curw = ls[i].original
				newl = ls[i+1].original
				nexw = ls[i+2].original
				# look for pattern: wordstart-, newline, restofword.
				
				if (((newl == u'_NEWLINE_N_') or (newl == u'_NEWLINE_R_')) & ((curw[-1] == u'-') & (len(curw) > 1))):
					# check that: wordstart isn't in dictionary,
					# combining it with restofword is in dictionary,
					# and restofword doesn't start with capital letter
					# -- this is generally approximately good enough
					if (not self.punctuation.sub('', curw) in self.dictionary
						and self.punctuation.sub('', curw+nexw) in self.dictionary
						and nexw[0].islower()):
						# make a new row to put combined form into the output later
						ls[i] = {
							'Original': curw[:-1]+nexw,
							'1-best': curw[:-1]+nexw,
							'1-best prob.': 0.99,
							'2-best': '_PRE_COMBINED_',
							'2-best prob.': 1.11e-25,
							'3-best': '_PRE_COMBINED_',
							'3-best prob.': 1.11e-25,
							'4-best': '_PRE_COMBINED_',
							'4-best prob.': 1.11e-25,
						}
						ls[i+1] = {'Original': 'BLANK'}
						ls[i+2] = {'Original': 'BLANK'}
		return [lin for lin in ls if lin != u'BLANK']
	
	def evaluate(self, token):
		#self.log.debug(token)
		
		# this should not happen in well-formed input
		if len(token.original) == 0:
			return ('error', 'Input is malformed! Original is 0-length: {}'.format(token))
		
		# catch linebreaks
		if (token.original in [u'_NEWLINE_N_', u'_NEWLINE_R_']):
			return ('linefeed', None)
		
		# catch memorised corrections
		if not token.is_punctuation() and token.original in self.memos:
			return ('memo', self.memos[token.original])
		
		# k best candidate words
		filtids = [k for k, (c,p) in token.kbest() if c in self.dictionary]
		
		(bin, decision) = self.heuristics.evaluate(token)
		#self.log.debug('%d %s' % (bin, decisioncode))
		
		# return decision codes and output token form or candidate list as appropriate
		if decision == 'o':
			return ('original', token.original)
		elif decision == 'k':
			return ('kbest', 1)
		elif decision == 'd':
			return ('kdict', filtids[0])
		else:
			# decision is 'a' or undefined
			return ('annotator', filtids)


class CorrectionShell(cmd.Cmd):
	prompt = 'CorrectOCR> '
	
	def start(tokens, correcter, correctionTracking=defaultdict(int), intro=None):
		sh = CorrectionShell()
		sh.tokenwindow = splitwindow(tokens, before=7, after=7)
		sh.correcter = correcter
		sh.dictionary = sh.correcter.dictionary
		sh.k = sh.correcter.k
		sh.tracking = {
			'tokenCount': 0,
			'humanCount': 0,
			'tokenTotal': len(tokens),
			'newWords': [],
			'correctionTracking': correctionTracking,
		}
		sh.log = logging.getLogger(__name__+'.CorrectionShell')
		sh.punctuation = regex.compile(r'\p{posix_punct}+')
		sh.use_rawinput = True
		
		sh.cmdloop(intro)

		return sh.tracking
	
	def preloop(self):
		return self.nexttoken()
	
	def nexttoken(self):
		try:
			ctxr, self.token, ctxl = next(self.tokenwindow)
			if self.token.gold:
				return self.nexttoken()
			(self.decision, self.var) = self.correcter.evaluate(self.token)
			
			self.tracking['tokenCount'] += 1
			if self.decision == 'annotator':
				self.tracking['humanCount'] +=1 # increment human-effort count
				
				print('\n\n...{} \033[1;7m{}\033[0m {}...\n'.format(
					' '.join([c.gold or c.original for c in ctxr]),
					self.token.original,
					' '.join([c.original for c in ctxl])
				))
				print('\nSELECT for {} :\n'.format(self.token.original))
				for k, (candidate, probability) in self.token.kbest():
					print('\t{}. {} ({}){}\n'.format(k, candidate, probability,
						' * is in dictionary' if k in self.var else ''
					))
				
				self.prompt = 'CorrectOCR {}/{} ({}) > '.format(self.tracking['tokenCount'], self.tracking['tokenTotal'], self.tracking['humanCount'])
			else:
				self.cmdqueue.insert(0, '{} {}'.format(self.decision, self.var))
		except StopIteration:
			print('Reached end of tokens, going to quit...')
			return self.onecmd('quit')
	
	def select(self, word, decision, save=True):
		print('Selecting {} for "{}": "{}"'.format(decision, self.token.original, word))
		self.token.gold = word
		if save:
			cleanword = self.punctuation.sub('', word)
			if cleanword not in self.dictionary:
				self.tracking['newWords'].append(cleanword) # add to suggestions for dictionary review
			self.dictionary.add(cleanword) # add to current dictionary for subsequent heuristic decisions
			self.tracking['correctionTracking'][(self.punctuation.sub('', self.token.original), cleanword)] += 1
		return self.nexttoken()
	
	def emptyline(self):
		if self.lastcmd == 'original':
			return super().emptyline() # repeats by default
		else:
			pass # dont repeat other commands
	
	def do_original(self, arg):
		"""Choose original (abbreviation: o)"""
		return self.select(self.token.original, 'original')
	
	def do_shell(self, arg):
		"""Custom input to replace token"""
		return self.select(arg, 'user input')
	
	def do_kbest(self, arg):
		"""Choose k-best by number (abbreviation: just the number)"""
		if arg:
			k = int(arg[0]) 
		else:
			k = 1
		(candidate, _) = self.token.kbest(k)
		return self.select(candidate, '{}-best'.format(k))
	
	def do_kdict(self, arg):
		"""Choose k-best which is in dictionary"""
		(candidate, _) = self.token.kbest(int(arg))
		return self.select(candidate, 'k-best from dict')
	
	def do_memo(self, arg):
		return self.select(arg, 'memoized correction')
	
	def do_error(self, arg):
		self.log.error('ERROR: {} {}'.format(arg, str(self.token)))
	
	def do_linefeed(self, arg):
		return self.select('\n', 'linefeed', save=False)
	
	def do_defer(self, arg):
		"""Defer decision for another time."""
		print('Deferring decision...')
		return self.nexttoken()
	
	def do_quit(self, arg):
		return True
	
	def default(self, line):
		if line == 'o':
			return self.onecmd('original')
		elif line == 'k':
			return self.onecmd('kbest 1')
		elif line.isnumeric():
			return self.onecmd('kbest '+line)
		elif line == 'q':
			return self.onecmd('quit')
		elif line == 'p':
			print(self.decision, self.var, self.token) # for debugging
		else:
			self.log.error('bad command: "{}"'.format(line))
			return super().default(line)


def correct(settings):
	log = logging.getLogger(__name__+'.correct')
	
	# try to combine hyphenated linebreaks before correction
	linecombine = True
	
	# - - - parse inputs - - -
	
	log.info('Correcting ' + settings.fileid + ' ')
	origfilename = settings.originalPath.joinpath(settings.fileid + '.txt')
	
	# - - - set up files - - -
	
	# read memoized corrections
	with Path(settings.memoizedCorrectionsFile.name) as p:
		if p.is_file() and p.stat().st_size > 0:
			memos = json.load(settings.memoizedCorrectionsFile)
		else:
			log.info('no memoized corrections found!')
			memos = {}
	
	# read corrections learning file
	correctionTracking = defaultdict(int)
	with Path(settings.correctionTrackingFile.name) as p:
		if p.is_file() and p.stat().st_size > 0:
			with open_for_reading(p) as f:
				for key, count in json.load(f).items():
					(original, gold) = key.split('\t')
					correctionTracking[(original, gold)] = int(count)
				correctionTracking.update()
	
	log.debug(correctionTracking)
	
	# -----------------------------------------------------------
	# // -------------------------------------------- //
	# //  Interactively handle corrections in a file  //
	# // -------------------------------------------- //

	# open file to write corrected output
	# don't write over finished corrections
	correctfilename = ensure_new_file(settings.correctedPath.joinpath(settings.fileid + '.txt'))
	o = open(correctfilename, 'w', encoding='utf-8')

	# get metadata, if any
	if settings.nheaderlines > 0:
		with open_for_reading(origfilename) as f:
			metadata = f.readlines()[:settings.nheaderlines]
	else:
		metadata = ''

	# and write it to output file, replacing 'Corrected: No' with 'Yes'
	for l in metadata:
		o.write(l.replace(u'Corrected: No', u'Corrected: Yes'))

	# get tokens to use for correction
	tokens = tokenizer.tokenize(settings)
	
	dictionary = Dictionary(settings.dictionaryFile, settings.caseInsensitive)
	correcter = Correcter(dictionary, settings.heuristicSettingsFile,
	                      memos, settings.caseInsensitive, settings.k)
	
	if linecombine:
		tokens = correcter.linecombiner(tokens)

	# print info to annotator
	log.info(' file ' + settings.fileid + '  contains about ' + str(len(tokens)) + ' words')
	for l in metadata:
		log.info(l)
	
	tracking = CorrectionShell.start(tokens, correcter, correctionTracking)

	#log.debug(tokens)
	log.debug(tracking['newWords'])
	log.debug(tracking['correctionTracking'])

	# optionally clean up hyphenation in completed tokens
	if settings.dehyphenate:
		tokens = [dehyph(tk) for tk in tokens]

	# make print-ready text
	spaced = u' '.join([token.gold or token.original for token in tokens])
	despaced = spaced.replace('_NEWLINE_N_', '\n').replace(' \n ', '\n')

	# write corrected output
	o.write(despaced)
	o.close()
	
	# update tracking & memos of annotator's actions
	memos = dict()
	track = dict()
	for (original, gold), count in sorted(tracking['correctionTracking'].items(), key=lambda x: x[1], reverse=True):
		memos[original] = gold
		track[original +'\t'+ gold] = count
	with open(settings.correctionTrackingFile.name, 'w', encoding='utf-8') as f:
		json.dump(track, f)
	json.dump(memos, open(settings.memoizedCorrectionsFile.name, 'w'))

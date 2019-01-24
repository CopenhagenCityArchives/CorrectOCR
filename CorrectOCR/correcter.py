# coding=utf-8
# c richter / ricca@seas.upenn.edu
import regex
import cmd
import csv
import logging
from collections import defaultdict
from pathlib import Path

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
				curw = ls[i]['Original']
				newl = ls[i+1]['Original']
				nexw = ls[i+2]['Original']
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
	
	def evaluate(self, l):
		self.log.debug(l)
		
		# this should not happen in well-formed input
		if len(l['Original']) == 0:
			return ('error', 'Input is malformed! Original is 0-length: '+l)
		
		# catch linebreaks
		if (l['Original'] == u'_NEWLINE_N_') or (l['Original'] == u'_NEWLINE_R_'):
			return ('linefeed', None)
		
		# catch memorised corrections
		if (l['Original'] in self.memos):
			return ('memo', memodict[l['Original']])
		
		# k best candidate words
		kbws = [self.punctuation.sub('', l['{}-best'.format(n+1)]) for n in range(0, self.k)]
		filtws = [kww for kww in kbws if kww in self.dictionary]
		filtids = [nn for nn, kww in enumerate(kbws) if kww in self.dictionary]
		
		(bin, decision) = self.heuristics.evaluate(l)
		#self.log.debug('%d %s' % (bin, decisioncode))
		
		# return decision codes and output token form or candidate list as appropriate
		if decision == 'o':
			return ('original', l['Original'])
		elif decision == 'k':
			return ('kbest', 1)
		elif decision == 'd':
			return ('kdict', filtids[0])
		elif decision == 'a':
			return ('annotator', filtids)
		else:
			return ('error', 'Unknown decision returned from heuristics: ' + decision)


class CorrectionShell(cmd.Cmd):
	prompt = 'CorrectOCR> '
	
	def start(tokens, correcter, k=4, intro=None):
		sh = CorrectionShell()
		sh.tokenwindow = splitwindow(tokens, before=7, after=7)
		sh.correcter = correcter
		sh.dictionary = sh.correcter.dictionary
		sh.memos = sh.correcter.memos
		sh.k = k
		sh.humanCount = 0
		sh.tokenlist = []
		sh.newdictwords = []
		sh.trackdict = defaultdict(int)
		sh.log = logging.getLogger(__name__+'.CorrectionShell')
		sh.punctuation = regex.compile(r'\p{posix_punct}+')

		sh.cmdloop(intro)

		return sh.humanCount, sh.tokenlist, sh.newdictwords, sh.trackdict
	
	def nexttoken(self):
		try:
			ctxr, self.token, ctxl = next(self.tokenwindow)
			(decision, var) = self.correcter.evaluate(self.token)
			
			if decision == 'annotator':
				self.humanCount +=1 # increment human-effort count
				
				print('\n\n{} \033[1;7m{}\033[0m {}\n'.format(
					' '.join([c['Original'] for c in ctxr]),
					self.token['Original'],
					' '.join([c['Original'] for c in ctxl])
				))
				print('\nSELECT for {} :\n'.format(self.token['Original']))
				for kn in range(1, self.k+1):
					print('\t{}. {} ({}){}\n'.format(
						kn,
						self.token['{}-best'.format(kn)],
						self.token['{}-best prob.'.format(kn)],
						' * is in dictionary' if kn in var else ''
					))
			else:
				self.onecmd('{} {}'.format(decision, var))
			
			return False # continue
		except StopIteration:
			return True # shouldStop
	
	def emptyline(self):
		if self.lastcmd == 'original':
			return self.onecmd(self.lastcmd) # repeat
		else:
			pass # dont repeat other commands
	
	def preloop(self):
		return self.nexttoken()
	
	def do_original(self, arg):
		"""Choose original"""
		print('Selecting original: '+self.token['Original'])
		self.tokenlist.append(arg) # add to output tokenlist
		cleanword = self.punctuation.sub('', arg.lower())
		self.newdictwords.append(cleanword) # add to suggestions for dictionary review
		self.dictionary.add(cleanword) # add to temp dict for the rest of this file
		self.trackdict[(self.token['Original'], arg)] += 1 # track annotator's choice
	
	def do_shell(self, arg):
		"""Custom input to replace token""" #TODO currently !-prefix is needed, drop that?
		print('Selecting user input: '+arg)
		self.tokenlist.append(arg)
		self.dictionary.add(arg)
		self.trackdict[(self.token['Original'], arg)] += 1
	
	def do_kbest(self, arg):
		"""Choose k-best"""
		if arg:
			k = int(arg[0]) 
		else:
			k = 1
		kbest = self.token['{}-best'.format(k)]
		print('Selecting {}-best: {}'.format(k, kbest))
		self.tokenlist.append(kbest)
		self.trackdict[(self.token['Original'], kbest)] += 1
	
	def do_kdict(self, arg):
		print('Selecting k-best from dict: '+self.token['{}-best'.format(arg)])
		self.tokenlist.append(self.token['{}-best'.format(arg)])
	
	def do_memo(self, arg):
		print('Selecting memoized correction: '+arg)
		self.tokenlist.append(arg)
		self.trackdict[(self.token['Original'], arg)] += 1
	
	def do_error(self, arg):
		self.log.error('ERROR: {} {}'.format(arg, str(self.token)))
	
	def do_linefeed(self, arg):
		self.tokenlist.append('\n')
	
	def default(self, line):
		if line == 'o':
			return self.onecmd('original')
		elif line.isnumeric():
			return self.onecmd('kbest '+line)
		else:
			return super().default(line)
	
	def postcmd(self, stop, line):
		return stop or self.nexttoken()


def correct(settings):
	log = logging.getLogger(__name__+'.correct')
	
	# try to combine hyphenated linebreaks before correction
	linecombine = True
	
	# annotator key controls
	# can replace o, O, *, A, N with other keypress choices
	annkey = { #TODO
		'orig': 'o',
		'origSkipDictadd': 'O',
		'numescape': '*',
		'forceDictadd': 'A',
		'newln': 'N'
	}
	
	# - - - parse inputs - - -
	
	log.info('Correcting ' + settings.fileid + ' ')
	origfilename = settings.originalPath + settings.fileid + '.txt'
	decodefilename = settings.decodedPath + settings.fileid + '_decoded.csv'
	
	# - - - set up files - - -
	
	# read memorised corrections
	try:
		memofile = [l[:-1] for l in settings.memoizedPath.readlines()]
		memodict = {}
		for l in memofile:
			memodict[l.split(u'\t')[0]] = l.split(u'\t')[1]
		memos = set(memodict.keys())
	except:
		log.info('no memoized corrections found!')
		memos = {}
	
	# read corrections learning file
	try:
		trackfilelines = [l[:-1] for l in settings.correctionTrackingPath.readlines()]
		trackdict = defaultdict(int)
		for l in trackfilelines:
			li = l.split(u'\t')
			trackdict[(u'\t').join(li[:2])] = int(li[2])
		trackfile.close()
	except:
		trackdict = defaultdict(int)

	# -----------------------------------------------------------
	# // -------------------------------------------- //
	# //  Interactively handle corrections in a file  //
	# // -------------------------------------------- //

	# open file to write corrected output
	# don't write over finished corrections
	correctfilename = settings.correctfilename or (settings.correctedPath + 'c_' + settings.fileid + '.txt')
	correctfilename = ensure_new_file(correctfilename)
	o = open(correctfilename, 'w', encoding='utf-8')

	# get metadata, if any
	if settings.nheaderlines > 0:
		with open_for_reading(origfilename) as f:
			mtd = f.readlines()[:settings.nheaderlines]
	else:
		mtd = ''

	# and write it to output file, replacing 'Corrected: No' with 'Yes'
	for l in mtd:
		o.write(l.replace(u'Corrected: No', u'Corrected: Yes'))

	# get decodings to use for correction
	log.info('Opening decoded file: '+decodefilename)
	with open_for_reading(decodefilename) as f:
		dec = list(csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE, quotechar=''))
	
	dictionary = Dictionary(settings.dictionaryFile, settings.caseInsensitive)
	correcter = Correcter(dictionary, settings.heuristicSettingsFile,
	                      memos, settings.caseInsensitive, settings.k)
	
	if linecombine:
		dec = correcter.linecombiner(dec)

	# print info to annotator
	log.info(' file ' + settings.fileid + '  contains about ' + str(len(dec)) + ' words')
	for l in mtd:
		log.info(l)

	# track count of tokens seen by human
	huct = 0

	tokenlist = [] # build list of output tokens
	newdictwords = [] # potential additions to dictionary, after review

	(humanCount, tokenlist, newdictwords, trackdict) = CorrectionShell.start(dec, correcter, settings.k)

	log.debug(tokenlist)
	log.debug(newdictwords)

	# optionally clean up hyphenation in completed tokenlist
	if settings.dehyphenate:
		tokenlist = [dehyph(tk) for tk in tokenlist]

	# make print-ready text
	spaced = u' '.join(tokenlist)
	despaced = spaced.replace(u' \n ', u'\n')

	# write corrected output
	o.write(despaced)
	o.close()

	# output potential new words to review for dictionary addition
	with open(settings.dictpotentialname, 'w', encoding='utf-8') as f:
		f.write(u'ANNOTATOR JUDGEMENT ' + str(huct) + ' TOKENS OF ABOUT ' + str(len(dec)) + ' IN FILE.\n')
		f.write('\n'.join(newdictwords))

	# update tracking of annotator's actions
	newstats = sorted(trackdict, key=trackdict.__getitem__, reverse=True)
	with open(settings.learningfilename, 'w', encoding='utf-8') as f:
		for ent in newstats:
			f.write(ent + u'\t' + str(trackdict[ent]) + u'\n')

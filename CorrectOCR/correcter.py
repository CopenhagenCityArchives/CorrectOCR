# coding=utf-8
import glob
import regex
import sys
import argparse
import os
import random
import string
from collections import defaultdict
# c richter / ricca@seas.upenn.edu

import csv
import logging

from . import open_for_reading, splitwindow
from .dictionary import Dictionary

'''
IMPORTANT BEFORE USING:
To display interactive text your environment must be compatible with the encoding.
For example:
> export LANG=is_IS.UTF-8
> export LC_ALL=is_IS.UTF-8
> locale
'''


class Correcter(object):
	def __init__(self, dictionary, conv, heuristicSettings, memos, caseInsensitive=False, k=4):
		self.caseInsensitive = caseInsensitive
		self.conv = conv
		self.heuristicSettings = heuristicSettings
		self.memos = memos
		self.k = k
		self.log = logging.getLogger(__name__+'.Correcter')
		self.dictionary = dictionary
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
					if (((not(self.dictionary.contains(self.punctuation.sub('', curw)))) & (self.dictionary.contains(self.punctuation.sub('', curw+nexw)))) & (nexw[0].islower())):
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
	
	def determine_bin(self, token, dcode):
		# original form
		original = self.punctuation.sub('', token['Original'])
		
		# top k best
		k1 = token['1-best']
		
		# evaluate candidates against the dictionary
		
		oind = self.dictionary.contains(original) #orig in dict?
		k1ind = self.dictionary.contains(k1) #k1 in dict?
		
		# k1 = orig and this is in dict.
		if ((original == k1) & oind):
			return 1
		
		# k1 = orig but not in dict, and no other kbest in dict either
		if ((original == k1) & (not oind)) & (dcode == 'zerokd'):
			return 2
		
		# k1 = orig but not in dict, but some lower-ranked kbest is in dict
		if ((original == k1) & (not oind)) & (dcode == 'somekd'):
			return 3
		
		# k1 is different from orig, and k1 passes dict check while orig doesn't
		if ((original != k1) & (not oind)) & k1ind:
			return 4
		
		# k1 is different from orig and nothing anywhere passes dict check
		if ((original != k1) & (not oind)) & (dcode == 'zerokd'):
			return 5
		
		# k1 is different from orig and neither is in dict, but a lower-ranked candidate is
		if ((original != k1) & (not oind)) & ((not k1ind) & (dcode == 'somekd')):
			return 6
		
		# k1 is different from orig and both are in dict
		if ((original != k1) & oind) & k1ind:
			return 7
		
		# k1 is different from orig, orig is in dict and no candidates are in dict
		if ((original != k1) & oind) & (dcode == 'zerokd'):
			return 8
		
		# k1 is different from orig, k1 not in dict but a lower candidate is
		#   and orig also in dict
		if ((original != k1) & oind) & ((not k1ind) & (dcode == 'somekd')):
			return 9
		
	def codeline(self, l):
		self.log.debug(l)
		
		# this should not happen in well-formed input
		if len(l['Original']) == 0:
			return ('ZEROERROR', None)
		
		# catch linebreaks
		if (l['Original'] == u'_NEWLINE_N_') or (l['Original'] == u'_NEWLINE_R_'):
			return ('LN', u'\n')
		
		# catch memorised corrections
		if (l['Original'] in self.memos):
			return ('MEMO', [l['Original'], memodict[l['Original']]])
		
		# k best candidate words
		kbws = [self.punctuation.sub('', l['{}-best'.format(n+1)]) for n in range(0, self.k)]
		
		# number of k-best that are in the dictionary
		nkdict = len(set([kww for kww in kbws if self.dictionary.contains(kww)]))
		
		# create dictionary-filtered candidate list if appropriate
		filtws = []
		if nkdict == 0:
			dcode = 'zerokd'
		if nkdict == 4:
			dcode = 'allkd'
		if 0 < nkdict < 4:
			dcode = 'somekd'
			filtws = [kww for kww in kbws if self.dictionary.contains(kww)]
			filtids = [nn for nn, kww in enumerate(kbws) if self.dictionary.contains(kww)]
		
		decision = self.conv[self.heuristicSettings[self.determine_bin(l, dcode)]]
		
		# return decision codes and output token form or candidate list as appropriate
		if decision == 'ORIG':
			return ('ORIG', l['Original'])
		elif decision == 'K1':
			return ('K1', l['1-best'])
		elif decision == 'KDICT':
			return ('KDICT', l['{}-best'.format(filtids[0])])
		elif decision == 'ANNOT':
			if l['Original'] == l['1-best']:
				return ('ANNOT', [l['{}-best'.format(n+1)] for n in range(0, self.k)])
			else:
				return ('ANNOT', [l['Original']] + [l['{}-best'.format(n+1)] for n in range(0, self.k)])
		elif decision == 'UNK':
			return ('NULLERROR', None)


def correct(settings):
	log = logging.getLogger(__name__+'.correct')
	
	punctuation = regex.compile(r'\p{posix_punct}+')
	
	caseSens = True
	kn = 4
	
	# try to combine hyphenated linebreaks before correction
	linecombine = True
	
	# naming convention for HMM decoding files
	decodeext = '_decoded.csv'
	
	# decision code conversion dictionary
	conv = {'o': 'ORIG', 'a': 'ANNOT', 'k': 'K1', 'd': 'KDICT'}
	
	# annotator key controls
	# can replace o, O, *, A, N with other keypress choices
	annkey = {'orig': 'o', 'origSkipDictadd': 'O',
           'numescape': '*', 'forceDictadd': 'A', 'newln': 'N'}
	
	# - - - parse inputs - - -
	
	log.info('Correcting ' + settings.fileid + ' ')
	origfilename = settings.originalPath + settings.fileid + '.txt'
	decodefilename = settings.decodedPath + settings.fileid + decodeext
	
	# - - - set up files - - -
	
	# read heuristic settings
	settfile = [l[:-1] for l in settings.heuristicSettingsPath.readlines()]
	heuristicSettings = {}
	for l in settfile:
		heuristicSettings[int(l.split(u'\t')[0])] = l.split(u'\t')[1]
	
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
		trackfile = settings.correctionTrackingPath
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
	if os.path.isfile(correctfilename):
		correctfilename = correctfilename[:-4] + '_' + ''.join([random.choice(string.ascii_letters + string.digits) for n in range(8)]) + '.txt'
		log.info('Corrected file already exists! Renaming to avoid overwriting.')
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
	
	dictionary = Dictionary(settings.dictionaryPath, settings.caseInsensitive)
	correcter = Correcter(dictionary, conv, heuristicSettings,
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
	
	# - - -
	# - - - process each token in decoded input - - -
	for cxl, lin, cxr in splitwindow(dec, before=7, after=7):
		# get heuristic decision for how to handle token
		handle = correcter.codeline(lin)

	 # use decision outcomes as indicated
	
		if handle[0] in ['LN', 'ORIG', 'K1', 'KDICT']:
			tokenlist.append(handle[1])
		elif handle[0] == 'MEMO': # memorised correction - keep track of how many times it is used
			tokenlist.append(handle[1][1])
			trackdict[u'\t'.join([handle[1][0], handle[1][1]])] += 1
		elif 'ERROR' in handle[0]:
			log.error('\n\n' + handle[0] + ': That should not have happened! Line:'+str(lin))

		elif handle[0] == 'ANNOT':
			huct +=1 # increment human-effort count
			print('\n\n'+' '.join([c['Original'] for c in cxl]) + ' \033[1;7m ' + handle[1][0] + ' \033[0m ' + ' '.join([c['Original'] for c in cxr])) # print sentence

			print('\nSELECT for ' + handle[1][0] + ' :')
			for u in range(min(kn, (len(handle[1])-1))):
				print('\n\t' + str(u+1) + '.  ' + handle[1][u+1]) # print choices

			ipt = input('> ')
		
			if (ipt == annkey['orig']) | (ipt == ''):
				tokenlist.append(handle[1][0]) # add to output tokenlist
				cleanword = punctuation.sub('', handle[1][0].lower())
				newdictwords.append(cleanword) # add to suggestions for dictionary review
				dictionary.add(cleanword) # add to temp dict for the rest of this file
				trackdict[u'\t'.join([handle[1][0], handle[1][0]])] += 1 # track annotator's choice
			
			# DO NOT add to temp dict for the rest of this file
			elif (ipt == annkey['origSkipDictadd']):
				tokenlist.append(handle[1][0])
				trackdict[u'\t'.join([handle[1][0], handle[1][0]])] += 1
			elif ipt in [str(nb) for nb in range(1, kn+1)]: # annotator picked a number 1-k
				tokenlist.append(handle[1][int(ipt)])
				trackdict[u'\t'.join([handle[1][0], handle[1][int(ipt)]])] += 1

			else: # annotator typed custom input
				# escape numbers 1-k:
				# enter '*1' to output the token '1' instead of select candidate #1
				if ((ipt[0] == annkey['numescape']) & (ipt[1:].isdigit())):
					ipt = ipt[1:]
				if ipt[-1] == annkey['forceDictadd']: # add this new input form to dictionary if specified
					ipt = ipt[:-1]
					cleanword = punctuation.sub('', ipt.lower())
					if ipt[-1] == annkey['newln']:
						cleanword = punctuation.sub('', ipt[:-1].lower())
					newdictwords.append(cleanword)
					dws.add(cleanword)
				if ipt[-1] == annkey['newln']: # add new linebreak following token, if specified
					tokenlist.append(ipt[:-1] + '\n')
					trackdict[u'\t'.join([handle[1][0][:-1], ipt[:-1]])] += 1
				else:
					tokenlist.append(ipt)
					trackdict[u'\t'.join([handle[1][0], ipt])] += 1

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

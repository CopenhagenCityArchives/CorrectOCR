# coding=utf-8
import codecs, glob, regex, sys, argparse, os, random, string
from collections import defaultdict
# c richter / ricca@seas.upenn.edu

import logging

from . import open_for_reading
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
	def __init__(self, dictionary, conv, binsettings, memos, caseInsensitive=False, k=4):
		self.caseInsensitive = caseInsensitive
		self.conv = conv
		self.binsettings = binsettings
		self.memos = memos
		self.k = k
		self.log = logging.getLogger(__name__+'.Correcter')
		self.dictionary = dictionary
	

	# - - -
	# hyphenation
	# - - - 

	# remove selected hyphens from inside a single token - postprocessing step
	def dehyph(self, tk):
		punctuation = regex.compile(r'\p{posix_punct}+')

		o = tk
		# if - in token, and token is not only punctuation, and - is not at end or start of token:
		if (u'-' in tk) & ((len(punctuation.sub('', tk)) > 0) & ((tk[-1] != u'-') & (tk[0] != u'-')) ):
			# if - doesn't precede capital letter, and the word including dash form isn't in dictionary:
			if ((not tk[tk.index(u'-')+1].isupper()) & ((not tk in dws) & (not tk.lower() in dws))):
				# if the word not including dash form is in dictionary, only then take out the dash
				if (( punctuation.sub('', tk) in dws) or (  punctuation.sub('', tk).lower() in dws)):
					o = tk.replace(u'-',u'')
		return(o)


	# try putting together some lines that were split by hyphenation - preprocessing step
	def linecombiner(self, ls):
		punctuation = regex.compile(r'\p{posix_punct}+')

		for i in range(len(ls) - 2):
			if (ls[i] != u'BLANK'):
				curw = ls[i].split('\t')[0]
				newl = ls[i+1].split('\t')[0]
				nexw = ls[i+2].split('\t')[0]
				# look for pattern: wordstart-, newline, restofword.
		
				if (((newl == u'_NEWLINE_N_') or (newl == u'_NEWLINE_R_')) & ((curw[-1] == u'-') & (len(curw) > 1)) ):
	# check that: wordstart isn't in dictionary,
	# combining it with restofword is in dictionary,
	# and restofword doesn't start with capital letter -- this is generally approximately good enough
					if ( ((not(self.dictionary.contains(punctuation.sub('', curw)))) & (self.dictionary.contains(punctuation.sub('', curw+nexw)))) & (nexw[0].islower())):
	# make a new row to put combined form into the output later
						newrw = (u'\t').join([curw[:-1]+nexw,curw[:-1]+nexw,curw[:-1]+nexw,u'.99',u'_PRE_COMBINED_',u'1.11e-25',u'_PRE_COMBINED_',u'1.11e-25',u'_PRE_COMBINED_',u'1.11e-25'])
						newrw += u'\r\n'
						ls[i] = newrw
						ls[i+1] = u'BLANK'
						ls[i+2] = u'BLANK'
		return [lin for lin in ls if lin != u'BLANK']



	# -----------------------------------------------------------

	# // --------------------- //
	# //   Process ONE TOKEN   //
	# // --------------------- //


	def codeline(self, i, ln):
		punctuation = regex.compile(r'\p{posix_punct}+')

		self.log.debug('%d: %s' % (i,str(ln)))
	# - - -

		# setup
		decision = 'UNK'
		l = ln.replace(u'\r\n','').split('\t')

	# - - -

		# this should not happen in well-formed input
		if len(l[0]) == 0:
			return('ZEROERROR',None)

		# catch linebreaks
		if (l[0] == u'_NEWLINE_N_') or (l[0] == u'_NEWLINE_R_'):
			return('LN',u'\n')

		# catch memorised corrections
		if (l[0] in self.memos):
			return('MEMO',[l[0],memodict[l[0]]])

	# - - -
	# - - - check observable features of token - - -

	 # punctuation is considered not relevant

		# original form
		orig = punctuation.sub('', l[0])

		# k best candidate words
		kbws = [ punctuation.sub('', l[ix]) for ix in range(1,(self.k*2),2)]

		# top k best
		k1 = kbws[0]


	 # evaluate candidates against the dictionary

		# number of k-best that are in the dictionary
		nkdict = len(set([kww for kww in kbws if self.dictionary.contains(kww)]))

		oind = self.dictionary.contains(orig) #orig in dict?
		k1ind = self.dictionary.contains(k1) #k1 in dict?

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


	 #	EXAMPLE
	 #  an evidently useful quantity for sorting out what to send to annotators
	 # - difference ratio of k1 and k2 decoding probabilities 
	 #	qqh = (float(l[2])-float(l[4]))/float(l[2])



	# - - -
	# - - - BIN SORTING - - -
	#  sort each token into a bin
	#  and return that bin's decision as defined in settings file


	# bin 1
	# k1 = orig and this is in dict.
		if ((orig == k1) & oind):
			decision = self.conv[self.binsettings['1']]

	# bin 2
	# k1 = orig but not in dict, and no other kbest in dict either
		if ((orig == k1) & (not oind)) & (dcode == 'zerokd'):
			decision = self.conv[self.binsettings['2']]
	#		if (qqh <= .95):				# EXAMPLE using qqh with threshold to subdivide categories:
	#			decision = self.conv[self.binsettings['2a']]
	#		else:
	#			decision = self.conv[self.binsettings['2b']]

	# bin 3
	# k1 = orig but not in dict, but some lower-ranked kbest is in dict
		if ((orig == k1) & (not oind)) & (dcode == 'somekd'):
			decision = self.conv[self.binsettings['3']]

	# bin 4
	# k1 is different from orig, and k1 passes dict check while orig doesn't
		if ((orig != k1) & (not oind)) & k1ind:
			decision = self.conv[self.binsettings['4']]

	# bin 5
	# k1 is different from orig and nothing anywhere passes dict check
		if ((orig != k1) & (not oind)) & (dcode == 'zerokd'):
			decision = self.conv[self.binsettings['5']]

	# bin 6
	# k1 is different from orig and neither is in dict, but a lower-ranked candidate is
		if ((orig != k1) & (not oind)) & ((not k1ind) & (dcode == 'somekd')):
			decision = self.conv[self.binsettings['6']]

	# bin 7
	# k1 is different from orig and both are in dict
		if ((orig != k1) & oind) & k1ind:
			decision = self.conv[self.binsettings['7']]
		
	# bin 8
	# k1 is different from orig, orig is in dict and no candidates are in dict
		if ((orig != k1) & oind) & (dcode == 'zerokd'):
			decision = self.conv[self.binsettings['8']]

	# bin 9
	# k1 is different from orig, k1 not in dict but a lower candidate is
	#   and orig also in dict
		if ((orig != k1) & oind) & ((not k1ind) & (dcode == 'somekd')):
			decision = self.conv[self.binsettings['9']]

	# return decision codes and output token form or candidate list as appropriate
		if decision == 'ORIG':
			return('ORIG',l[0])
		elif decision == 'K1':
			return('K1',l[1])
		elif decision == 'KDICT':
			return('KDICT',l[(2*filtids[0])+1])
		elif decision == 'ANNOT':
			if l[0] == l[1]:
				return('ANNOT',l[1:len(l):2])
			else:
				return('ANNOT',([l[0]] + l[1:len(l):2]))
		elif decision == 'UNK':
			return('NULLERROR',None)

# - - -
# for interface
# - - -

# fetchcontext should give to 15 words to either side of target word,
# or stop at file boundaries
def fetchcontext(n,dec,tokenlist):
	lbound = max((n - 15),0)
	ubound = min((n + 15),len(dec))
	return (tokenlist[lbound:n], [ln.split('\t')[0] for ln in dec[(n+1):ubound]])

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
	conv = {'o':'ORIG','a':'ANNOT','k':'K1','d':'KDICT'}

	# annotator key controls
	# can replace o, O, *, A, N with other keypress choices
	annkey = {'orig':'o','origSkipDictadd':'O','numescape':'*','forceDictadd':'A','newln':'N'}

	# - - - parse inputs - - -

	log.info('* * * * * CORRECTING   '  + settings.fileid + ' ')
	origfilename = settings.origtxtdir + settings.fileid + '.txt'
	decodefilename = settings.decodecsvdir + settings.fileid + decodeext

	# - - - set up files - - -

	# read heuristic settings
	settfile = [l[:-1] for l in settings.settingsfile.readlines()]
	binsettings = {}
	for l in settfile:
		binsettings[l.split(u'\t')[0]] = l.split(u'\t')[1]

	# read memorised corrections
	try:
		memofile = [l[:-1] for l in settings.memofilename.readlines()]
		memodict = {}
		for l in memofile:
			memodict[l.split(u'\t')[0]] = l.split(u'\t')[1]
		memos = set(memodict.keys())
	except:
		log.info('no memorised corrections found!')
		memos = {}

	# read corrections learning file
	try:
		trackfile = settings.learningfilename
		trackfilelines = [l[:-1] for l in settings.learningfilename.readlines()]
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
	correctfilename = settings.correctfilename or (settings.correctdir + 'c_' + settings.fileid + '.txt')
	if os.path.isfile(correctfilename):
		correctfilename = correctfilename[:-4] + '_' + ''.join([random.choice(string.ascii_letters + string.digits) for n in range(8)]) + '.txt'
		log.info('Corrected file already exists! Renaming to avoid overwriting.')
	o = open(correctfilename, 'w', encoding='utf-8')

	# get metadata, if any
	if settings.nheaderlines > 0:
		mtdf = open(origfilename, 'r', encoding='utf-8')
		mtd = mtdf.readlines()[:settings.nheaderlines]
		mtdf.close()
	else:
		mtd = ''

	# and write it to output file, replacing 'Corrected: No' with 'Yes'
	for l in mtd:
		o.write(l.replace(u'Corrected: No',u'Corrected: Yes'))


	# get decodings to use for correction
	with open(decodefilename, 'r', encoding='utf-8') as f:
		log.info('opening : '+decodefilename)
		dec = f.readlines()[1:]

	log.debug(dec[:5])

	dictionary = Dictionary(settings.dictionary, settings.caseInsensitive)
	correcter = Correcter(dictionary, conv, binsettings, memos, settings.caseInsensitive, settings.k)
	
	if linecombine:
		dec = correcter.linecombiner(dec)

	# print info to annotator
	log.info(' file ' + settings.fileid + '  contains about ' + str(len(dec)) + ' words')
	for l in mtd:
		log.info(l)

	# track count of tokens seen by human
	huct=0

	tokenlist = [] # build list of output tokens
	newdictwords = [] # potential additions to dictionary, after review
	
	# - - -
	# - - - process each token in decoded input - - -
	for (i, lin) in enumerate(dec):
		handle = correcter.codeline(i, lin) # get heuristic decision for how to handle token

	 # use decision outcomes as indicated
	
		if handle[0] in ['LN','ORIG','K1','KDICT']:
			tokenlist.append(handle[1])
		elif handle[0] == 'MEMO': # memorised correction - keep track of how many times it is used
			tokenlist.append(handle[1][1])
			trackdict[u'\t'.join([handle[1][0],handle[1][1]])] += 1
		elif 'ERROR' in handle[0]:
			log.error('\n\n' + handle[0] + ': That should not have happened!\nLine '+str(i)+' print:\n'+ u' # '.join(lin.split(u'\t')) )

		elif handle[0] == 'ANNOT':
			huct +=1 # increment human-effort count
			(cxl, cxr) = fetchcontext(i,dec,tokenlist) # get context words to display
			print('\n\n'+' '.join(cxl) + ' \033[1;7m ' + handle[1][0] + ' \033[0m ' + ' '.join(cxr)) # print sentence

			print('\nSELECT for ' + handle[1][0] + ' :')
			for u in range(min(kn,(len(handle[1])-1))):
				print('\n\t' + str(u+1) + '.  ' + handle[1][u+1]) # print choices

			ipt = input('> ')
		
			if (ipt == annkey['orig']) | (ipt == ''):
				tokenlist.append(handle[1][0]) # add to output tokenlist
				cleanword = punctuation.sub('', handle[1][0].lower())
				newdictwords.append(cleanword) # add to suggestions for dictionary review
				dictionary.add(cleanword) # add to temp dict for the rest of this file
				trackdict[u'\t'.join([handle[1][0],handle[1][0]])] += 1 # track annotator's choice
			
			elif (ipt == annkey['origSkipDictadd']): # DO NOT add to temp dict for the rest of this file
				tokenlist.append(handle[1][0])
				trackdict[u'\t'.join([handle[1][0],handle[1][0]])] += 1
			elif ipt in [str(nb) for nb in range(1,kn+1)]: # annotator picked a number 1-k
				tokenlist.append(handle[1][int(ipt)])
				trackdict[u'\t'.join([handle[1][0],handle[1][int(ipt)]])] += 1

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
					trackdict[u'\t'.join([handle[1][0][:-1],ipt[:-1]])] += 1
				else:
					tokenlist.append(ipt)
					trackdict[u'\t'.join([handle[1][0],ipt])] += 1


	# optionally clean up hyphenation in completed tokenlist
	if settings.dehyphenate:
		tokenlist = [dehyph(tk) for tk in tokenlist]

	# make print-ready text
	spaced = u' '.join(tokenlist)
	despaced = spaced.replace(u' \n ',u'\n')

	# write corrected output
	o.write(despaced)
	o.close()

	# output potential new words to review for dictionary addition
	dictpotential = codecs.open(settings.dictpotentialname, 'w', 'utf-8')
	dictpotential.write(u'ANNOTATOR JUDGEMENT ' + str(huct) + ' TOKENS OF ABOUT ' + str(len(dec)) + ' IN FILE.\n')
	dictpotential.write('\n'.join(newdictwords))
	dictpotential.close()

	# update tracking of annotator's actions
	newstats = sorted(trackdict, key=trackdict.__getitem__, reverse=True)
	trackfile = codecs.open(settings.learningfilename, 'w', 'utf-8')
	for ent in newstats:
		trackfile.write(ent + u'\t' + str(trackdict[ent]) + u'\n')
	trackfile.close()

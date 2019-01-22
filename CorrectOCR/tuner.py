# coding=utf-8
import glob
import regex
import collections
# c richter / ricca@seas.upenn.edu

import logging

from . import open_for_reading
from .dictionary import Dictionary


class Tuner(object):
	def __init__(self, dictionaryPath, caseInsensitive=False, k=4):
		self.caseInsensitive = caseInsensitive
		self.k = k
		self.log = logging.getLogger(__name__+'.Tuner')
		self.dictionary = Dictionary(dictionaryPath, caseInsensitive)
		with open_for_reading(dictionaryPath) as f:
			dictfile = f.readlines()
			dwl = [] # dictionary-words-list
			for line in dictfile:
				for word in line.split():
					if self.caseInsensitive:
						dwl.append(word.lower())
					else:
						dwl.append(word)
			self.dws = set(dwl) # dictionary-words-set
	
	#-------------------------------------
	# measure
	# - - -

	# handle one token.
	def codeline(self, vs, i, ln):
		punctuation = regex.compile(r'\p{posix_punct}+')
	
		if self.caseInsensitive:
			ln = ln.lower()
		l = ln.replace(u'\r\n', '').split('\t')
		
		self.log.debug(l)
		# strip punctuation, which is considered not relevant to evaluation
		gold = punctuation.sub('', l[0]) # gold standard wordform
		orig = punctuation.sub('', l[1]) # original uncorrected wordform

		# if the 1st or 2nd input column is empty, a word segmentation error probably occurred in the original
		# (though possibly a deletion)
		# don't count any other errors here; they will be counted in the segmentation error's other line.
		if ((l[1] == '') & (len(gold) > 0)):
			vs[29] += 1 # words ran together in original / undersegmentation
			return vs

		if ((l[0] == '') & (len(orig) > 0)):
			vs[30] += 1 # word wrongly broken apart in original / oversegmentation
			return vs

		if len(gold) == 0: # after having stripped punctuation the length is 0
			return vs # don't count it, since punctuation doesn't matter
	
		vs[0] += 1
		# total number of real tokens - controlled for segmentation errors

		# k best candidate words
		kbws = [punctuation.sub('', l[ix]) for ix in range(2, (self.k*2)+1, 2)]

		# accompanying probabilities, if wanted
		#kbprobs = [ l[ix] for ix in range(3,(self.k*2)+2,2)]

		# best candidate
		k1 = kbws[0]

		# number of distinct k-best words that pass the dictionary check
		nkdict = len(set([kww for kww in kbws if self.dictionary.contains(kww)]))

		# code type of candidates' dict membership
		if nkdict == 0:
			dcode = 'zerokd'
		if nkdict == len(set(kbws)):
			dcode = 'allkd'

		filtws = [] # filtered words - only candidates that pass dict check
		if 0 < nkdict < len(set(kbws)):
			dcode = 'somekd'
			filtws = [kww for kww in kbws if self.dictionary.contains(kww)]
			d1 = filtws[0]

		# code - does orig pass dict check? does k1?
		oind = self.dictionary.contains(orig)
		k1ind = self.dictionary.contains(k1)

		# an evidently useful quantity for sorting out what to send to annotators
		#  - can split any existing category across a threshold of this quantity
		#	(based on probabilities of best and 2nd-best decoded candidates)
		qqh = (float(l[3])-float(l[5]))/float(l[3])

		# ---------- tracked categories (bins)
		#   as defined by features observable at correction time,
		#   with results for each bin reported wrt matching gold standard

		#bins = [defaultdict(int)] * 9

		# bin 1
		# k1 = orig and this is in dict.
		if ((orig == k1) & oind) & (orig == gold):
			vs[1] += 1
			vs[28] += 1
		if ((orig == k1) & oind) & (orig != gold):
			vs[2] += 1
			vs[28] += 1

		# bin 2
		# k1 = orig but not in dict, and no other kbest in dict either
		if ((orig == k1) & (not oind)) & (dcode == 'zerokd'):
			if (orig == gold):
				vs[3] += 1
				#if (qqh <= .95): # EXAMPLE using qqh with threshold to subdivide categories
				#	vs[31] += 1
				#else:
				#	vs[32] += 1
				vs[28] += 1
			if (orig != gold):
				vs[4] += 1
				#if (qqh <= .95): # EXAMPLE
				#	vs[33] += 1
				#else:
				#	vs[34] += 1
				vs[28] += 1

		# bin 3
		# k1 = orig but not in dict, but some lower-ranked kbest is in dict
		if ((orig == k1) & (not oind)) & (dcode == 'somekd'):

			if (k1 == gold):
				vs[5] += 1
				vs[28] += 1

			# if highest-probability word that passes dict check = gold
			elif (d1 == gold):
				vs[6] += 1
				vs[28] += 1
		
			else:
				vs[7] += 1
				vs[28] += 1

		# bin 4
		# k1 is different from orig, and k1 passes dict check while orig doesn't
		if ((orig != k1) & (not oind)) & k1ind:
	
			if (orig == gold):
				vs[8] += 1
				vs[28] += 1
	
			elif (k1 == gold):
				vs[9] += 1
				vs[28] += 1

			# neither orig nor k1 forms are correct
			else:
				vs[10] += 1
				vs[28] += 1

		# bin 5
		# k1 is different from orig and nothing anywhere passes dict check
		if ((orig != k1) & (not oind)) & (dcode == 'zerokd'):
	
			if (orig == gold):
				vs[11] += 1
				vs[28] += 1
	
			elif (k1 == gold):
				vs[12] += 1
				vs[28] += 1

			else:
				vs[13] += 1
				vs[28] += 1

		# bin 6
		# k1 is different from orig and neither is in dict, but a lower-ranked candidate is
		if ((orig != k1) & (not oind)) & ((not k1ind) & (dcode == 'somekd')):

			# orig is correct although not in dict
			if (orig == gold):
				vs[14] += 1
				vs[28] += 1

			# k1 is correct although not in dict
			elif (k1 == gold):
				vs[15] += 1
				vs[28] += 1

			# best dictionary-filtered candidate is correct
			elif (d1 == gold):
				vs[16] += 1
				vs[28] += 1

			else:
				vs[17] += 1
				vs[28] += 1

		# bin 7
		# k1 is different from orig and both are in dict
		if ((orig != k1) & oind) & k1ind:
	
			if (orig == gold):
				vs[18] += 1
				vs[28] += 1
	
			elif (k1 == gold):
				vs[19] += 1
				vs[28] += 1

			else:
				vs[20] += 1
				vs[28] += 1

		# bin 8
		# k1 is different from orig, orig is in dict and no candidates are in dict
		if ((orig != k1) & oind) & (dcode == 'zerokd'):
	
			if (orig == gold):
				vs[21] += 1
				vs[28] += 1
	
			elif (k1 == gold):
				vs[22] += 1
				vs[28] += 1

			else:
				vs[23] += 1
				vs[28] += 1

		# bin 9
		# k1 is different from orig, k1 not in dict but a lower candidate is
		#   and orig also in dict
		if ((orig != k1) & oind) & ((not k1ind) & (dcode == 'somekd')):
	
			if (orig == gold):
				vs[24] += 1
				vs[28] += 1
	
			elif (k1 == gold):
				vs[25] += 1
				vs[28] += 1

			elif (d1 == gold):
				vs[26] += 1
				vs[28] += 1
		
			else:
				vs[27] += 1
				vs[28] += 1
	
		return vs


def tune(settings):
	# print percents nicely
	def percc(n, x):
		if n == 0:
			return '00'
		return str(round((n/x)*100, 2))
	
	#-------------------------------------
	# gather stats on devset
	# - - -

	# read in csv data
	lns1 = []
	for filename in glob.glob(settings.devDecodedPath + '/*.csv'):
		print(filename)
		with open_for_reading(filename) as f:
			lns1.append(f.readlines()[1:])
	lns = [val for sublist in lns1 for val in sublist]

	# variables to track - see output file for interpretation
	vs = [0]*35
	
	tuner = Tuner(settings.dictionary, settings.caseInsensitive, settings.k)
	
	# sort each token
	for (i, lin) in enumerate(lns):
		vs = tuner.codeline(vs, i, lin)
	
	# write - - -
	outf = open(settings.outfile, 'w', encoding='utf-8')
	outf.write('Tokens included in evaluation: \t n = ' + str(vs[0])+'\n\n')
	outf.write('INITIAL ERROR - ' + str(vs[2]+vs[4]+vs[6]+vs[7]+vs[9]+vs[10]+vs[12]+vs[13]+vs[15]+vs[16]+vs[17]+vs[19]+vs[20]+vs[22]+vs[23]+vs[25]+vs[26]+vs[27]) +
	           '  (' + percc((vs[2]+vs[4]+vs[6]+vs[7]+vs[9]+vs[10]+vs[12]+vs[13]+vs[15]+vs[16]+vs[17]+vs[19]+vs[20]+vs[22]+vs[23]+vs[25]+vs[26]+vs[27]), vs[0]) + ' %) \n\n\n')
	outf.write('Choose from these options for each bin:  a (annotator), o (original), k (k1, best candidate), d (best candidate in dictionary)\n  (o and k interchangeable when original is identical to k1; d not applicable in all bins)\n\n\n\n')

	outf.write('BIN 1 \t\t decision?\t\n')
	outf.write(' k1 same as original, and in dictionary\n')
	outf.write(percc((vs[1]+vs[2]), vs[0]) + ' % of tokens\n')
	outf.write('tokens where k1/orig == gold? \t ' +
	           str(vs[1]) + '  (' + percc(vs[1], vs[0]) + ' %)\n')
	outf.write('tokens where k1/orig != gold? \t ' +
	           str(vs[2]) + '  (' + percc(vs[2], vs[0]) + ' %)\n\n\n')

	outf.write('BIN 2 \t\t decision?\t\n')
	outf.write(
		' k1 same as original and not in dict, and no lower-ranked decoding candidate in dict either\n')
	outf.write(percc((vs[3]+vs[4]), vs[0]) + ' % of tokens\n')
	outf.write('tokens where k1/orig == gold? \t ' +
	           str(vs[3]) + '  (' + percc(vs[3], vs[0]) + ' %)\n')
	#outf.write('\tof these, tokens under threshold:\t '+ str(vs[31]) + '  (' + percc(vs[31],vs[0]) + ' %)\n') # EXAMPLE
	#outf.write('\tof these, tokens over threshold:\t '+ str(vs[32]) + '  (' + percc(vs[32],vs[0]) + ' %)\n')
	outf.write('tokens where k1/orig != gold? \t ' +
	           str(vs[4]) + '  (' + percc(vs[4], vs[0]) + ' %)\n')
	#outf.write('\tof these, tokens under threshold:\t '+ str(vs[33]) + '  (' + percc(vs[33],vs[0]) + ' %)\n')
	#outf.write('\tof these, tokens over threshold:\t '+ str(vs[34]) + '  (' + percc(vs[34],vs[0]) + ' %)\n')
	outf.write('\n\n\n')

	outf.write('BIN 3 \t\t decision?\t\n')
	outf.write(
		' k1 same as original and not in dict, but a lower-ranked candidate is in dict\n')
	outf.write(percc((vs[5]+vs[6]+vs[7]), vs[0]) + ' % of tokens\n')
	outf.write('tokens where orig == gold? \t ' +
	           str(vs[5]) + '  (' + percc(vs[5], vs[0]) + ' %)  \n')
	outf.write('tokens where top dict-filtered candidate == gold? \t ' +
	           str(vs[6]) + '  (' + percc(vs[6], vs[0]) + ' %)  \n')
	outf.write('tokens where gold is neither orig nor top dict-filtered? \t ' +
	           str(vs[7]) + '  (' + percc(vs[7], vs[0]) + ' %)   \n\n\n\n')

	outf.write('BIN 4 \t\t decision?\t\n')
	outf.write(' k1 different from original, original not in dict but k1 is\n')
	outf.write(percc((vs[8]+vs[9]+vs[10]), vs[0]) + ' % of tokens\n')
	outf.write('tokens where orig == gold? \t ' +
	           str(vs[8]) + '  (' + percc(vs[8], vs[0]) + ' %)\n')
	outf.write('tokens where k1 == gold? \t ' +
	           str(vs[9]) + '  (' + percc(vs[9], vs[0]) + ' %)\n')
	outf.write('tokens where neither orig nor k1 == gold? \t ' +
	           str(vs[10]) + '  (' + percc(vs[10], vs[0]) + ' %)\n\n\n')

	outf.write('BIN 5 \t\t decision?\t\n')
	outf.write(
		' k1 different from original, neither original nor any decoding candidate is in dict\n')
	outf.write(percc((vs[11]+vs[12]+vs[13]), vs[0]) + ' % of tokens\n')
	outf.write('tokens where orig == gold? \t ' +
	           str(vs[11]) + '  (' + percc(vs[11], vs[0]) + ' %)\n')
	outf.write('tokens where k1 == gold? \t ' +
	           str(vs[12]) + '  (' + percc(vs[12], vs[0]) + ' %)\n')
	outf.write('tokens where neither orig nor k1 == gold? \t ' +
	           str(vs[13]) + '  (' + percc(vs[13], vs[0]) + ' %)\n\n\n')

	outf.write('BIN 6 \t\t decision?\t\n')
	outf.write(
		'  k1 different from original, neither original nor k1 are in dict but some lower candidate is\n')
	outf.write(percc((vs[14]+vs[15]+vs[16]+vs[17]), vs[0]) + ' % of tokens\n')
	outf.write('tokens where orig == gold? \t ' +
	           str(vs[14]) + '  (' + percc(vs[14], vs[0]) + ' %)\n')
	outf.write('tokens where k1 == gold? \t ' +
	           str(vs[15]) + '  (' + percc(vs[15], vs[0]) + ' %)\n')
	outf.write('tokens where top dict-filtered candidate == gold? \t ' +
	           str(vs[16]) + '  (' + percc(vs[16], vs[0]) + ' %)\n')
	outf.write('tokens where gold is neither orig nor k1 nor top dict-filtered? \t ' +
	           str(vs[17]) + '  (' + percc(vs[17], vs[0]) + ' %)\n\n\n')

	outf.write('BIN 7 \t\t decision?\t\n')
	outf.write(' k1 is different from original and both are in dict\n')
	outf.write(percc((vs[18]+vs[19]+vs[20]), vs[0]) + ' % of tokens\n')
	outf.write('tokens where orig == gold? \t ' +
	           str(vs[18]) + '  (' + percc(vs[18], vs[0]) + ' %)\n')
	outf.write('tokens where k1 == gold? \t ' +
	           str(vs[19]) + '  (' + percc(vs[19], vs[0]) + ' %)\n')
	outf.write('tokens where neither orig nor k1 == gold? \t ' +
	           str(vs[20]) + '  (' + percc(vs[20], vs[0]) + ' %)\n\n\n')

	outf.write('BIN 8 \t\t decision?\t\n')
	outf.write(
		' k1 is different from original, original is in dict while no candidates k1 or lower are in dict\n')
	outf.write(percc((vs[21]+vs[22]+vs[23]), vs[0]) + ' % of tokens\n')
	outf.write('tokens where orig == gold? \t ' +
	           str(vs[21]) + '  (' + percc(vs[21], vs[0]) + ' %)\n')
	outf.write('tokens where k1 == gold? \t ' +
	           str(vs[22]) + '  (' + percc(vs[22], vs[0]) + ' %)\n')
	outf.write('tokens where neither orig nor k1 == gold? \t ' +
	           str(vs[23]) + '  (' + percc(vs[23], vs[0]) + ' %)\n\n\n')

	outf.write('BIN 9 \t\t decision?\t\n')
	outf.write(' k1 is different from original and is not in dict, while both original and some lower-ranked candidate are in dict\n')
	outf.write(percc((vs[24]+vs[25]+vs[26]+vs[27]), vs[0]) + ' % of tokens\n')
	outf.write('tokens where orig == gold? \t ' +
	           str(vs[24]) + '  (' + percc(vs[24], vs[0]) + ' %)\n')
	outf.write('tokens where k1 == gold? \t ' +
	           str(vs[25]) + '  (' + percc(vs[25], vs[0]) + ' %)\n')
	outf.write('tokens where top dict-filtered candidate == gold? \t ' +
	           str(vs[26]) + '  (' + percc(vs[26], vs[0]) + ' %)\n')
	outf.write('tokens where none of the above == gold? \t ' +
	           str(vs[27]) + '  (' + percc(vs[27], vs[0]) + ' %)\n')


def make_settings(settings):
	# read report
	bins = [ln for ln in settings.reportPath.readlines() if "BIN" in ln]
	
	# write settings
	with open(settings.outfile, 'w', encoding='utf-8') as outf:
		for b in bins:
			binID = b.split()[1]
			action = b.split()[-1]
			outf.write(binID + u'\t' + action + u'\n')

# coding=utf-8
import glob
import regex
import csv
# c richter / ricca@seas.upenn.edu

import logging

from . import open_for_reading
from .dictionary import Dictionary
from .heuristics import Heuristics


# print percents nicely
def percc(n, x):
	if n == 0:
		return '00'
	return str(round((n/x)*100, 2))

class Tuner(object):
	def __init__(self, dictionary, caseInsensitive=False, k=4):
		self.caseInsensitive = caseInsensitive
		self.variables = [0]*35 # see report for interpretation
		self.k = k
		self.log = logging.getLogger(__name__+'.Tuner')
		self.dictionary = dictionary
		self.heuristics = Heuristics(self.dictionary, dict()) # settings not needed here and indeed may not be available yet
		self.punctuation = regex.compile(r'\p{posix_punct}+')
	
	def evaluate(self, l):
		vs = self.variables
		
		self.log.debug(l)
		# strip punctuation, which is considered not relevant to evaluation
		gold = self.punctuation.sub('', l['Gold']) # gold standard wordform
		orig = self.punctuation.sub('', l['Original']) # original uncorrected wordform

		# if the 1st or 2nd input column is empty, a word segmentation error probably occurred in the original
		# (though possibly a deletion)
		# don't count any other errors here; they will be counted in the segmentation error's other line.
		if ((l['Original'] == '') & (len(gold) > 0)):
			vs[29] += 1 # words ran together in original / undersegmentation
			vs = self.variables
			return

		if ((l['Gold'] == '') & (len(orig) > 0)):
			vs[30] += 1 # word wrongly broken apart in original / oversegmentation
			vs = self.variables
			return

		if len(gold) == 0: # after having stripped punctuation the length is 0
			vs = self.variables # don't count it, since punctuation doesn't matter
			return
	
		vs[0] += 1
		# total number of real tokens - controlled for segmentation errors

		# k best candidate words
		kbws = [self.punctuation.sub('', l['{}-best'.format(n+1)]) for n in range(0, self.k)]

		# best candidate
		k1 = kbws[0]

		# number of distinct k-best words that pass the dictionary check
		nkdict = len(set([kww for kww in kbws if kww in self.dictionary]))

		# code type of candidates' dict membership
		if nkdict == 0:
			dcode = 'zerokd'
		if nkdict == len(set(kbws)):
			dcode = 'allkd'

		filtws = [] # filtered words - only candidates that pass dict check
		if 0 < nkdict < len(set(kbws)):
			dcode = 'somekd'
			filtws = [kww for kww in kbws if kww in self.dictionary]
			d1 = filtws[0]

		# an evidently useful quantity for sorting out what to send to annotators
		#  - can split any existing category across a threshold of this quantity
		#	(based on probabilities of best and 2nd-best decoded candidates)
		qqh = (float(l['1-best prob.'])-float(l['2-best prob.']))/float(l['1-best prob.'])

		# ---------- tracked categories (bins)
		#   as defined by features observable at correction time,
		#   with results for each bin reported wrt matching gold standard
		
		(bin,_) = self.heuristics.evaluate(l, dcode)
		
		if bin == 1:
			# k1 = orig and this is in dict.
			if orig == gold:
				vs[1] += 1
				vs[28] += 1
			else:
				vs[2] += 1
				vs[28] += 1
		elif bin == 2:
			# k1 = orig but not in dict, and no other kbest in dict either
			if orig == gold:
				vs[3] += 1
				vs[28] += 1
			else:
				vs[4] += 1
				vs[28] += 1
		elif bin == 3:
			# k1 = orig but not in dict, but some lower-ranked kbest is in dict
			if k1 == gold:
				vs[5] += 1
				vs[28] += 1
			elif d1 == gold:
				# if highest-probability word that passes dict check = gold
				vs[6] += 1
				vs[28] += 1
			else:
				vs[7] += 1
				vs[28] += 1
		elif bin == 4:
			# k1 is different from orig, and k1 passes dict check while orig doesn't
			if orig == gold:
				vs[8] += 1
				vs[28] += 1
			elif k1 == gold:
				vs[9] += 1
				vs[28] += 1
			else:
				# neither orig nor k1 forms are correct
				vs[10] += 1
				vs[28] += 1
		elif bin == 5:
			# k1 is different from orig and nothing anywhere passes dict check
			if orig == gold:
				vs[11] += 1
				vs[28] += 1
			elif k1 == gold:
				vs[12] += 1
				vs[28] += 1
			else:
				vs[13] += 1
				vs[28] += 1
		elif bin == 6:
			# k1 is different from orig and neither is in dict, but a lower-ranked candidate is
			# orig is correct although not in dict
			if orig == gold:
				vs[14] += 1
				vs[28] += 1
			# k1 is correct although not in dict
			elif k1 == gold:
				vs[15] += 1
				vs[28] += 1
			# best dictionary-filtered candidate is correct
			elif d1 == gold:
				vs[16] += 1
				vs[28] += 1
			else:
				vs[17] += 1
				vs[28] += 1
		elif bin == 7:
			# k1 is different from orig and both are in dict
			if orig == gold:
				vs[18] += 1
				vs[28] += 1
			elif k1 == gold:
				vs[19] += 1
				vs[28] += 1
			else:
				vs[20] += 1
				vs[28] += 1
		elif bin == 8:
			# k1 is different from orig, orig is in dict and no candidates are in dict
			if orig == gold:
				vs[21] += 1
				vs[28] += 1
			elif k1 == gold:
				vs[22] += 1
				vs[28] += 1
			else:
				vs[23] += 1
				vs[28] += 1
		elif bin == 9:
			# k1 is different from orig, k1 not in dict but a lower candidate is
			# and orig also in dict
			if orig == gold:
				vs[24] += 1
				vs[28] += 1
			elif k1 == gold:
				vs[25] += 1
				vs[28] += 1
			elif d1 == gold:
				vs[26] += 1
				vs[28] += 1
			else:
				vs[27] += 1
				vs[28] += 1
		
		self.variables = vs
	
	def report(self):
		vs = self.variables
		out = []
		
		out.append('Tokens included in evaluation: \t n = ' + str(vs[0])+'\n\n')
		out.append('INITIAL ERROR - ' + str(vs[2]+vs[4]+vs[6]+vs[7]+vs[9]+vs[10]+vs[12]+vs[13]+vs[15]+vs[16]+vs[17]+vs[19]+vs[20]+vs[22]+vs[23]+vs[25]+vs[26]+vs[27]) +
				   '  (' + percc((vs[2]+vs[4]+vs[6]+vs[7]+vs[9]+vs[10]+vs[12]+vs[13]+vs[15]+vs[16]+vs[17]+vs[19]+vs[20]+vs[22]+vs[23]+vs[25]+vs[26]+vs[27]), vs[0]) + ' %) \n\n\n')
		out.append('Choose from these options for each bin:  a (annotator), o (original), k (k1, best candidate), d (best candidate in dictionary)\n  (o and k interchangeable when original is identical to k1; d not applicable in all bins)\n\n\n\n')

		out.append('BIN 1 \t\t decision?\t\n')
		out.append(' k1 same as original, and in dictionary\n')
		out.append(percc((vs[1]+vs[2]), vs[0]) + ' % of tokens\n')
		out.append('tokens where k1/orig == gold? \t ' +
				   str(vs[1]) + '  (' + percc(vs[1], vs[0]) + ' %)\n')
		out.append('tokens where k1/orig != gold? \t ' +
				   str(vs[2]) + '  (' + percc(vs[2], vs[0]) + ' %)\n\n\n')

		out.append('BIN 2 \t\t decision?\t\n')
		out.append(
			' k1 same as original and not in dict, and no lower-ranked decoding candidate in dict either\n')
		out.append(percc((vs[3]+vs[4]), vs[0]) + ' % of tokens\n')
		out.append('tokens where k1/orig == gold? \t ' +
				   str(vs[3]) + '  (' + percc(vs[3], vs[0]) + ' %)\n')
		#out.append('\tof these, tokens under threshold:\t '+ str(vs[31]) + '  (' + percc(vs[31],vs[0]) + ' %)\n') # EXAMPLE
		#out.append('\tof these, tokens over threshold:\t '+ str(vs[32]) + '  (' + percc(vs[32],vs[0]) + ' %)\n')
		out.append('tokens where k1/orig != gold? \t ' +
				   str(vs[4]) + '  (' + percc(vs[4], vs[0]) + ' %)\n')
		#out.append('\tof these, tokens under threshold:\t '+ str(vs[33]) + '  (' + percc(vs[33],vs[0]) + ' %)\n')
		#out.append('\tof these, tokens over threshold:\t '+ str(vs[34]) + '  (' + percc(vs[34],vs[0]) + ' %)\n')
		out.append('\n\n\n')

		out.append('BIN 3 \t\t decision?\t\n')
		out.append(
			' k1 same as original and not in dict, but a lower-ranked candidate is in dict\n')
		out.append(percc((vs[5]+vs[6]+vs[7]), vs[0]) + ' % of tokens\n')
		out.append('tokens where orig == gold? \t ' +
				   str(vs[5]) + '  (' + percc(vs[5], vs[0]) + ' %)  \n')
		out.append('tokens where top dict-filtered candidate == gold? \t ' +
				   str(vs[6]) + '  (' + percc(vs[6], vs[0]) + ' %)  \n')
		out.append('tokens where gold is neither orig nor top dict-filtered? \t ' +
				   str(vs[7]) + '  (' + percc(vs[7], vs[0]) + ' %)   \n\n\n\n')

		out.append('BIN 4 \t\t decision?\t\n')
		out.append(' k1 different from original, original not in dict but k1 is\n')
		out.append(percc((vs[8]+vs[9]+vs[10]), vs[0]) + ' % of tokens\n')
		out.append('tokens where orig == gold? \t ' +
				   str(vs[8]) + '  (' + percc(vs[8], vs[0]) + ' %)\n')
		out.append('tokens where k1 == gold? \t ' +
				   str(vs[9]) + '  (' + percc(vs[9], vs[0]) + ' %)\n')
		out.append('tokens where neither orig nor k1 == gold? \t ' +
				   str(vs[10]) + '  (' + percc(vs[10], vs[0]) + ' %)\n\n\n')

		out.append('BIN 5 \t\t decision?\t\n')
		out.append(
			' k1 different from original, neither original nor any decoding candidate is in dict\n')
		out.append(percc((vs[11]+vs[12]+vs[13]), vs[0]) + ' % of tokens\n')
		out.append('tokens where orig == gold? \t ' +
				   str(vs[11]) + '  (' + percc(vs[11], vs[0]) + ' %)\n')
		out.append('tokens where k1 == gold? \t ' +
				   str(vs[12]) + '  (' + percc(vs[12], vs[0]) + ' %)\n')
		out.append('tokens where neither orig nor k1 == gold? \t ' +
				   str(vs[13]) + '  (' + percc(vs[13], vs[0]) + ' %)\n\n\n')

		out.append('BIN 6 \t\t decision?\t\n')
		out.append(
			'  k1 different from original, neither original nor k1 are in dict but some lower candidate is\n')
		out.append(percc((vs[14]+vs[15]+vs[16]+vs[17]), vs[0]) + ' % of tokens\n')
		out.append('tokens where orig == gold? \t ' +
				   str(vs[14]) + '  (' + percc(vs[14], vs[0]) + ' %)\n')
		out.append('tokens where k1 == gold? \t ' +
				   str(vs[15]) + '  (' + percc(vs[15], vs[0]) + ' %)\n')
		out.append('tokens where top dict-filtered candidate == gold? \t ' +
				   str(vs[16]) + '  (' + percc(vs[16], vs[0]) + ' %)\n')
		out.append('tokens where gold is neither orig nor k1 nor top dict-filtered? \t ' +
				   str(vs[17]) + '  (' + percc(vs[17], vs[0]) + ' %)\n\n\n')

		out.append('BIN 7 \t\t decision?\t\n')
		out.append(' k1 is different from original and both are in dict\n')
		out.append(percc((vs[18]+vs[19]+vs[20]), vs[0]) + ' % of tokens\n')
		out.append('tokens where orig == gold? \t ' +
				   str(vs[18]) + '  (' + percc(vs[18], vs[0]) + ' %)\n')
		out.append('tokens where k1 == gold? \t ' +
				   str(vs[19]) + '  (' + percc(vs[19], vs[0]) + ' %)\n')
		out.append('tokens where neither orig nor k1 == gold? \t ' +
				   str(vs[20]) + '  (' + percc(vs[20], vs[0]) + ' %)\n\n\n')

		out.append('BIN 8 \t\t decision?\t\n')
		out.append(
			' k1 is different from original, original is in dict while no candidates k1 or lower are in dict\n')
		out.append(percc((vs[21]+vs[22]+vs[23]), vs[0]) + ' % of tokens\n')
		out.append('tokens where orig == gold? \t ' +
				   str(vs[21]) + '  (' + percc(vs[21], vs[0]) + ' %)\n')
		out.append('tokens where k1 == gold? \t ' +
				   str(vs[22]) + '  (' + percc(vs[22], vs[0]) + ' %)\n')
		out.append('tokens where neither orig nor k1 == gold? \t ' +
				   str(vs[23]) + '  (' + percc(vs[23], vs[0]) + ' %)\n\n\n')

		out.append('BIN 9 \t\t decision?\t\n')
		out.append(' k1 is different from original and is not in dict, while both original and some lower-ranked candidate are in dict\n')
		out.append(percc((vs[24]+vs[25]+vs[26]+vs[27]), vs[0]) + ' % of tokens\n')
		out.append('tokens where orig == gold? \t ' +
				   str(vs[24]) + '  (' + percc(vs[24], vs[0]) + ' %)\n')
		out.append('tokens where k1 == gold? \t ' +
				   str(vs[25]) + '  (' + percc(vs[25], vs[0]) + ' %)\n')
		out.append('tokens where top dict-filtered candidate == gold? \t ' +
				   str(vs[26]) + '  (' + percc(vs[26], vs[0]) + ' %)\n')
		out.append('tokens where none of the above == gold? \t ' +
				   str(vs[27]) + '  (' + percc(vs[27], vs[0]) + ' %)\n')
		
		return out

def tune(settings):
	log = logging.getLogger(__name__+'.tune')
	
	tuner = Tuner(Dictionary(settings.dictionaryPath, settings.caseInsensitive), settings.caseInsensitive, settings.k)
	
	for filename in glob.glob(settings.devDecodedPath + '/*.csv'):
		log.info('Collecting stats from ' + filename)
		with open_for_reading(filename) as f:
			reader = csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE, quotechar='')
			for row in reader:
				tuner.evaluate(row)
	
	with open(settings.outfile, 'w', encoding='utf-8') as f:
		f.writelines(tuner.report())


def make_settings(settings):
	# read report
	bins = [ln for ln in settings.reportPath.readlines() if "BIN" in ln]
	
	# write settings
	with open(settings.outfile, 'w', encoding='utf-8') as outf:
		for b in bins:
			binID = b.split()[1]
			action = b.split()[-1]
			outf.write(binID + u'\t' + action + u'\n')

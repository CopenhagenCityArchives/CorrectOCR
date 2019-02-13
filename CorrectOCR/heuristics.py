import logging
from collections import OrderedDict

import progressbar

from . import punctuationRE, open_for_reading
from .dictionary import Dictionary


# print percents nicely
def percc(n, x):
	if n == 0:
		return '00'
	return str(round((n/x)*100, 2))

class Heuristics(object):
	bins = OrderedDict({
		1: {
			'description': 'k1 == original and both are in dictionary.',
			'matcher': lambda o, k, d, dcode: o == k and o in d,
			'heuristic': 'a', # send to annotator by default if no loaded settings
		},
		2: {
			'description': 'k1 == original but they are not in dictionary, and no other kbest is in dictionary either.',
			'matcher': lambda o, k, d, dcode: o == k and o not in d and dcode == 'zerokd',
			'heuristic': 'a',
		},
		3: {
			'description': 'k1 == original but they are not in dictionary, but some lower-ranked kbest is.',
			'matcher': lambda o, k, d, dcode: o == k and o not in d and dcode == 'somekd',
			'heuristic': 'a',
		},
		4: {
			'description': 'k1 != original and is in dictionary while original isn''t.',
			'matcher': lambda o, k, d, dcode: o == k and o not in d and k in d,
			'heuristic': 'a',
		},
		5: {
			'description': 'k1 != original and nothing is in dictionary.',
			'matcher': lambda o, k, d, dcode: o != k and o not in d and dcode == 'zerokd',
			'heuristic': 'a',
		},
		6: {
			'description': 'k1 != original and neither are in dictionary, but a lower-ranked candidate is.',
			'matcher': lambda o, k, d, dcode: o != k and o not in d and dcode == 'somekd',
			'heuristic': 'a',
		},
		7: {
			'description': 'k1 != original and both are in dictionary.',
			'matcher': lambda o, k, d, dcode: o != k and o in d and k in d,
			'heuristic': 'a',
		},
		8: {
			'description': 'k1 != original, original is in dictionary and no candidates are in dictionary.',
			'matcher': lambda o, k, d, dcode: o != k and o in d and dcode == 'zerokd',
			'heuristic': 'a',
		},
		9: {
			'description': 'k1 != original, k1 is not in dictionary but both original and a lower candidate are.',
			'matcher': lambda o, k, d, dcode: o != k and o in d and k not in d and dcode == 'somekd',
			'heuristic': 'a',
		}
	})
	
	def __init__(self, settings, dictionary, k=4):
		for (bin, code) in settings.items():
			self.bins[int(bin)]['heuristic'] = code
		for i, j in self.bins.items():
			j['number'] = i
		self.dictionary = dictionary
		self.k = k
		self.log = logging.getLogger(f'{__name__}.Heuristics')
		self.reportVariables = [0]*31 # see report for interpretation
	
	def evaluate(self, token):
		# original form
		original = punctuationRE.sub('', token.original)
		
		# top k best
		kbest = list(token.kbest())
		
		# k best candidate words
		nkdict = [c for k, (c,p) in token.kbest() if c in self.dictionary]
		
		# create dictionary-filtered candidate list if appropriate
		if len(nkdict) == 0:
			dcode = 'zerokd'
		elif len(nkdict) == self.k:
			dcode = 'allkd'
		elif 0 < len(nkdict) < self.k:
			dcode = 'somekd'
		
		#self.log.debug(f'{original} {kbest} {dcode}')
		
		for num, bin in self.bins.items():
			if bin['matcher'](original, kbest[0][1][0], self.dictionary, dcode):
				return (dict(bin), bin['heuristic'])
		
		self.log.critical(f'Unable to make decision for token: {token}')
		return (None, None)

	def add_to_report(self, token):
		vs = self.reportVariables
		
		# strip punctuation, which is considered not relevant to evaluation
		gold = punctuationRE.sub('', token.gold) # gold standard wordform
		orig = punctuationRE.sub('', token.original) # original uncorrected wordform

		# if the 1st or 2nd input column is empty, a word segmentation error probably occurred in the original
		# (though possibly a deletion)
		# don't count any other errors here; they will be counted in the segmentation error's other line.
		if ((token.original == '') & (len(gold) > 0)):
			vs[29] += 1 # words ran together in original / undersegmentation
			vs = self.reportVariables
			return

		if ((token.gold == '') & (len(orig) > 0)):
			vs[30] += 1 # word wrongly broken apart in original / oversegmentation
			vs = self.reportVariables
			return

		if len(gold) == 0: # after having stripped punctuation the length is 0
			vs = self.reportVariables # don't count it, since punctuation doesn't matter
			return
	
		# total number of real tokens - controlled for segmentation errors
		vs[0] += 1

		# k best candidate words
		kbws = [punctuationRE.sub('', token.kbest(n)[0]) for n in range(1, self.k+1)]

		# best candidate
		k1 = kbws[0]

		# number of distinct k-best words that pass the dictionary check
		nkdict = len(set([kww for kww in kbws if kww in self.dictionary]))

		filtws = [] # filtered words - only candidates that pass dict check
		d1 = None
		if 0 < nkdict < len(set(kbws)):
			filtws = [kww for kww in kbws if kww in self.dictionary]
			d1 = filtws[0]

		# an evidently useful quantity for sorting out what to send to annotators
		#  - can split any existing category across a threshold of this quantity
		#	(based on probabilities of best and 2nd-best candidates)
		# qqh = (token.kbest(1)[1]-token.kbest(2)[1]) / token.kbest(1)[1]

		# ---------- tracked categories (bins)
		#   as defined by features observable at correction time,
		#   with results for each bin reported wrt matching gold standard
		
		(bin,_) = self.evaluate(token)
		
		if bin['number'] == 1:
			# k1 = orig and this is in dict.
			if orig == gold:
				vs[1] += 1
			else:
				vs[2] += 1
		elif bin['number'] == 2:
			# k1 = orig but not in dict, and no other kbest in dict either
			if orig == gold:
				vs[3] += 1
			else:
				vs[4] += 1
		elif bin['number'] == 3:
			# k1 = orig but not in dict, but some lower-ranked kbest is in dict
			if k1 == gold:
				vs[5] += 1
			elif d1 == gold:
				# if highest-probability word that passes dict check = gold
				vs[6] += 1
			else:
				vs[7] += 1
		elif bin['number'] == 4:
			# k1 is different from orig, and k1 passes dict check while orig doesn't
			if orig == gold:
				vs[8] += 1
			elif k1 == gold:
				vs[9] += 1
			else:
				# neither orig nor k1 forms are correct
				vs[10] += 1
		elif bin['number'] == 5:
			# k1 is different from orig and nothing anywhere passes dict check
			if orig == gold:
				vs[11] += 1
			elif k1 == gold:
				vs[12] += 1
			else:
				vs[13] += 1
		elif bin['number'] == 6:
			# k1 is different from orig and neither is in dict, but a lower-ranked candidate is
			# orig is correct although not in dict
			if orig == gold:
				vs[14] += 1
			# k1 is correct although not in dict
			elif k1 == gold:
				vs[15] += 1
			# best dictionary-filtered candidate is correct
			elif d1 == gold:
				vs[16] += 1
			else:
				vs[17] += 1
		elif bin['number'] == 7:
			# k1 is different from orig and both are in dict
			if orig == gold:
				vs[18] += 1
			elif k1 == gold:
				vs[19] += 1
			else:
				vs[20] += 1
		elif bin['number'] == 8:
			# k1 is different from orig, orig is in dict and no candidates are in dict
			if orig == gold:
				vs[21] += 1
			elif k1 == gold:
				vs[22] += 1
			else:
				vs[23] += 1
		elif bin['number'] == 9:
			# k1 is different from orig, k1 not in dict but a lower candidate is
			# and orig also in dict
			if orig == gold:
				vs[24] += 1
			elif k1 == gold:
				vs[25] += 1
			elif d1 == gold:
				vs[26] += 1
			else:
				vs[27] += 1
		
		vs[28] += 1 # unused ?!
		
		self.reportVariables = vs

	def report(self):
		vs = self.reportVariables
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
			' k1 same as original and not in dict, and no lower-ranked candidate in dict either\n')
		out.append(percc((vs[3]+vs[4]), vs[0]) + ' % of tokens\n')
		out.append('tokens where k1/orig == gold? \t ' +
				   str(vs[3]) + '  (' + percc(vs[3], vs[0]) + ' %)\n')
		out.append('tokens where k1/orig != gold? \t ' +
				   str(vs[4]) + '  (' + percc(vs[4], vs[0]) + ' %)\n')
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
			' k1 different from original, neither original nor any candidate is in dict\n')
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

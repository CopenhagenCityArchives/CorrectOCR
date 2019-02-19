import logging
from collections import OrderedDict
from typing import Dict, Tuple, Any

from . import punctuationRE
from .dictionary import Dictionary
from .tokenize import Token


class Heuristics(object):
	log = logging.getLogger(f'{__name__}.Heuristics')

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
	
	def __init__(self, settings: Dict[int, str], dictionary: Dictionary, k=4):
		for (_bin, code) in settings.items():
			self.bins[int(_bin)]['heuristic'] = code
		for (number, _bin) in self.bins.items():
			_bin['number'] = number
		self.dictionary = dictionary
		self.k = k
		self.reportVariables = [0]*31 # see report for interpretation
	
	def evaluate(self, token: Token) -> Tuple[str, Any]:
		# original form
		original = punctuationRE.sub('', token.original)
		
		# top k best
		kbest = list(token.kbest())
		
		# k best candidate words
		nkdict = [c for k, (c,p) in token.kbest() if c in self.dictionary]
		
		# create dictionary-filtered candidate list if appropriate
		dcode = None
		if len(nkdict) == 0:
			dcode = 'zerokd'
		elif len(nkdict) == self.k:
			dcode = 'allkd'
		elif 0 < len(nkdict) < self.k:
			dcode = 'somekd'
		
		#Heuristics.log.debug(f'{original} {kbest} {dcode}')
		
		for num, _bin in self.bins.items():
			if _bin['matcher'](original, kbest[0][1][0], self.dictionary, dcode):
				return _bin['heuristic'], dict(_bin)
		
		Heuristics.log.critical(f'Unable to make decision for token: {token}')
		return 'a', None

	def add_to_report(self, token: Token):
		vs = self.reportVariables
		
		# strip punctuation, which is considered not relevant to evaluation
		gold = punctuationRE.sub('', token.gold) # gold standard wordform
		orig = punctuationRE.sub('', token.original) # original uncorrected wordform

		# if the 1st or 2nd input column is empty, a word segmentation error probably occurred in the original
		# (though possibly a deletion)
		# don't count any other errors here; they will be counted in the segmentation error's other line.
		if (token.original == '') & (len(gold) > 0):
			vs[29] += 1 # words ran together in original / undersegmentation
			return

		if (token.gold == '') & (len(orig) > 0):
			vs[30] += 1 # word wrongly broken apart in original / oversegmentation
			return

		if len(gold) == 0: # after having stripped punctuation the length is 0
			return
	
		# total number of real tokens - controlled for segmentation errors
		vs[0] += 1

		# k best candidate words
		kbws = [punctuationRE.sub('', token.kbest(n)[0]) for n in range(1, self.k+1)]

		# best candidate
		k1 = kbws[0]

		# number of distinct k-best words that pass the dictionary check
		nkdict = len(set([kww for kww in kbws if kww in self.dictionary]))

		# filtered words - only candidates that pass dict check
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
		
		(_, _bin) = self.evaluate(token)

		if not _bin:
			return # was unable to make heuristic decision
		
		if _bin['number'] == 1:
			# k1 = orig and this is in dict.
			if orig == gold:
				vs[1] += 1
			else:
				vs[2] += 1
		elif _bin['number'] == 2:
			# k1 = orig but not in dict, and no other kbest in dict either
			if orig == gold:
				vs[3] += 1
			else:
				vs[4] += 1
		elif _bin['number'] == 3:
			# k1 = orig but not in dict, but some lower-ranked kbest is in dict
			if k1 == gold:
				vs[5] += 1
			elif d1 == gold:
				# if highest-probability word that passes dict check = gold
				vs[6] += 1
			else:
				vs[7] += 1
		elif _bin['number'] == 4:
			# k1 is different from orig, and k1 passes dict check while orig doesn't
			if orig == gold:
				vs[8] += 1
			elif k1 == gold:
				vs[9] += 1
			else:
				# neither orig nor k1 forms are correct
				vs[10] += 1
		elif _bin['number'] == 5:
			# k1 is different from orig and nothing anywhere passes dict check
			if orig == gold:
				vs[11] += 1
			elif k1 == gold:
				vs[12] += 1
			else:
				vs[13] += 1
		elif _bin['number'] == 6:
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
		elif _bin['number'] == 7:
			# k1 is different from orig and both are in dict
			if orig == gold:
				vs[18] += 1
			elif k1 == gold:
				vs[19] += 1
			else:
				vs[20] += 1
		elif _bin['number'] == 8:
			# k1 is different from orig, orig is in dict and no candidates are in dict
			if orig == gold:
				vs[21] += 1
			elif k1 == gold:
				vs[22] += 1
			else:
				vs[23] += 1
		elif _bin['number'] == 9:
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

	def report(self) -> str:
		vs = self.reportVariables

		# print percents nicely
		def percc(n: int, x: int) -> str:
			if n == 0:
				return '00'
			return str(round((n/x)*100, 2))

		out = ''
		
		out += 'Tokens included in evaluation: \t n = ' + str(vs[0])+'\n\n'
		out += 'INITIAL ERROR - ' + str(vs[2]+vs[4]+vs[6]+vs[7]+vs[9]+vs[10]+vs[12]+vs[13]+vs[15]+vs[16]+vs[17]+vs[19]+vs[20]+vs[22]+vs[23]+vs[25]+vs[26]+vs[27])
		out += '  (' + percc((vs[2]+vs[4]+vs[6]+vs[7]+vs[9]+vs[10]+vs[12]+vs[13]+vs[15]+vs[16]+vs[17]+vs[19]+vs[20]+vs[22]+vs[23]+vs[25]+vs[26]+vs[27]), vs[0]) + ' %) \n\n\n'
		out += 'Choose from these options for each bin:  a (annotator), o (original), k (k1, best candidate), d (best candidate in dictionary)\n  (o and k interchangeable when original is identical to k1; d not applicable in all bins)\n\n\n\n'

		out += 'BIN 1 \t\t decision?\t\n'
		out += Heuristics.bins[1]['description'] + '\n'
		out += percc((vs[1]+vs[2]), vs[0]) + ' % of tokens\n'
		out += f'tokens where k1/orig == gold? \t {vs[1]} ({vs[1]/vs[0]:.2%})\n'
		out += f'tokens where k1/orig != gold? \t {vs[2]} ({vs[2]/vs[0]:.2%})\n'
		out += '\n\n\n'

		out += 'BIN 2 \t\t decision?\t\n'
		out += Heuristics.bins[2]['description'] + '\n'
		out += percc((vs[3]+vs[4]), vs[0]) + ' % of tokens\n'
		out += f'tokens where k1/orig == gold? \t {vs[3]} ({vs[3]/vs[0]:.2%})\n'
		out += f'tokens where k1/orig != gold? \t {vs[4]} ({vs[4]/vs[0]:.2%})\n'
		out += '\n\n\n'

		out += 'BIN 3 \t\t decision?\t\n'
		out += Heuristics.bins[3]['description'] + '\n'
		out += percc((vs[5]+vs[6]+vs[7]), vs[0]) + ' % of tokens\n'
		out += f'tokens where orig == gold? \t {vs[5]} ({vs[5]/vs[0]:.2%})\n'
		out += f'tokens where top dict-filtered candidate == gold? \t {vs[6]} ({vs[6]/vs[0]:.2%})\n'
		out += f'tokens where gold is neither orig nor top dict-filtered? \t {vs[7]} ({vs[7]/vs[0]:.2%})\n'
		out += '\n\n\n'

		out += 'BIN 4 \t\t decision?\t\n'
		out += Heuristics.bins[4]['description'] + '\n'
		out += percc((vs[8]+vs[9]+vs[10]), vs[0]) + ' % of tokens\n'
		out += f'tokens where orig == gold? \t {vs[8]}  ({vs[8]/vs[0]:.2%})\n'
		out += f'tokens where k1 == gold? \t {vs[9]} ({vs[9]/vs[0]:.2%})\n'
		out += f'tokens where neither orig nor k1 == gold? \t {vs[10]} ({vs[10]/vs[0]:.2%})\n'
		out += '\n\n\n'

		out += 'BIN 5 \t\t decision?\t\n'
		out += Heuristics.bins[5]['description'] + '\n'
		out += percc((vs[11]+vs[12]+vs[13]), vs[0]) + ' % of tokens\n'
		out += f'tokens where orig == gold? \t {vs[11]} ({vs[11]/vs[0]:.2%})\n'
		out += f'tokens where k1 == gold? \t {vs[12]} ({vs[12]/vs[0]:.2%})\n'
		out += f'tokens where neither orig nor k1 == gold? \t {vs[13]} ({vs[13]/vs[0]:.2%})\n'
		out += '\n\n\n'

		out += 'BIN 6 \t\t decision?\t\n'
		out += Heuristics.bins[6]['description'] + '\n'
		out += percc((vs[14]+vs[15]+vs[16]+vs[17]), vs[0]) + ' % of tokens\n'
		out += f'tokens where orig == gold? \t {vs[14]} ({vs[14]/vs[0]:.2%})\n'
		out += f'tokens where k1 == gold? \t {vs[15]} ({vs[15]/vs[0]:.2%})\n'
		out += f'tokens where top dict-filtered candidate == gold? \t {vs[16]} ({vs[16]/vs[0]:.2%})\n'
		out += f'tokens where gold is neither orig nor k1 nor top dict-filtered? \t {vs[17]} ({vs[17]/vs[0]:.2%})\n'
		out += '\n\n\n'

		out += 'BIN 7 \t\t decision?\t\n'
		out += Heuristics.bins[7]['description'] + '\n'
		out += percc((vs[18]+vs[19]+vs[20]), vs[0]) + ' % of tokens\n'
		out += f'tokens where orig == gold? \t {vs[18]} ({vs[18]/vs[0]:.2%})\n'
		out += f'tokens where k1 == gold? \t {vs[19]} ({vs[19]/vs[0]:.2%})\n'
		out += f'tokens where neither orig nor k1 == gold? \t {vs[20]} ({vs[20]/vs[0]:.2%})\n'
		out += '\n\n\n'

		out += 'BIN 8 \t\t decision?\t\n'
		out += Heuristics.bins[8]['description'] + '\n'
		out += percc((vs[21]+vs[22]+vs[23]), vs[0]) + ' % of tokens\n'
		out += f'tokens where orig == gold? \t {vs[21]} ({vs[21]/vs[0]:.2%})\n'
		out += f'tokens where k1 == gold? \t {vs[22]} ({vs[22]/vs[0]:.2%})\n'
		out += f'tokens where neither orig nor k1 == gold? \t {vs[23]} ({vs[23]/vs[0]:.2%})\n'
		out += '\n\n\n'

		out += 'BIN 9 \t\t decision?\t\n'
		out += Heuristics.bins[9]['description'] + '\n'
		out += percc((vs[24]+vs[25]+vs[26]+vs[27]), vs[0]) + ' % of tokens\n'
		out += f'tokens where orig == gold? \t {vs[24]} ({vs[24]/vs[0]:.2%})\n'
		out += f'tokens where k1 == gold? \t {vs[25]} ({vs[25]/vs[0]:.2%})\n'
		out += f'tokens where top dict-filtered candidate == gold? \t {vs[26]} ({vs[26]/vs[0]:.2%})\n'
		out += f'tokens where none of the above == gold? \t {vs[27]} ({vs[27]/vs[0]:.2%})\n'
		out += '\n\n\n'
		
		return out

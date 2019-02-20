import logging
from collections import OrderedDict, defaultdict
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
			'counts': defaultdict(int),
		},
		2: {
			'description': 'k1 == original but they are not in dictionary, and no other kbest is in dictionary either.',
			'matcher': lambda o, k, d, dcode: o == k and o not in d and dcode == 'zerokd',
			'heuristic': 'a',
			'counts': defaultdict(int),
		},
		3: {
			'description': 'k1 == original but they are not in dictionary, but some lower-ranked kbest is.',
			'matcher': lambda o, k, d, dcode: o == k and o not in d and dcode == 'somekd',
			'heuristic': 'a',
			'counts': defaultdict(int),
		},
		4: {
			'description': 'k1 != original and is in dictionary while original isn''t.',
			'matcher': lambda o, k, d, dcode: o == k and o not in d and k in d,
			'heuristic': 'a',
			'counts': defaultdict(int),
		},
		5: {
			'description': 'k1 != original and nothing is in dictionary.',
			'matcher': lambda o, k, d, dcode: o != k and o not in d and dcode == 'zerokd',
			'heuristic': 'a',
			'counts': defaultdict(int),
		},
		6: {
			'description': 'k1 != original and neither are in dictionary, but a lower-ranked candidate is.',
			'matcher': lambda o, k, d, dcode: o != k and o not in d and dcode == 'somekd',
			'heuristic': 'a',
			'counts': defaultdict(int),
		},
		7: {
			'description': 'k1 != original and both are in dictionary.',
			'matcher': lambda o, k, d, dcode: o != k and o in d and k in d,
			'heuristic': 'a',
			'counts': defaultdict(int),
		},
		8: {
			'description': 'k1 != original, original is in dictionary and no candidates are in dictionary.',
			'matcher': lambda o, k, d, dcode: o != k and o in d and dcode == 'zerokd',
			'heuristic': 'a',
			'counts': defaultdict(int),
		},
		9: {
			'description': 'k1 != original, k1 is not in dictionary but both original and a lower candidate are.',
			'matcher': lambda o, k, d, dcode: o != k and o in d and k not in d and dcode == 'somekd',
			'heuristic': 'a',
			'counts': defaultdict(int),
		}
	})

	def __init__(self, settings: Dict[int, str], dictionary: Dictionary):
		for (_bin, code) in settings.items():
			self.bins[int(_bin)]['heuristic'] = code
		for (number, _bin) in self.bins.items():
			_bin['number'] = number
		self.dictionary = dictionary
		self.tokenCount = 0
		self.totalCount = 0
		self.punctuationCount = 0
		self.nogoldCount = 0
		self.oversegmented = 0
		self.undersegmented = 0

	def evaluate(self, token: Token) -> Tuple[str, Any]:
		# original form
		original = punctuationRE.sub('', token.original)

		# k best candidate words that are in dictionary
		nkdict = [c for k, (c,p) in token.kbest() if c in self.dictionary]

		dcode = None
		if len(nkdict) == 0:
			dcode = 'zerokd'
		elif 0 < len(nkdict) < token.k:
			dcode = 'somekd'
		elif len(nkdict) == token.k:
			dcode = 'allkd'

		for num, _bin in self.bins.items():
			if _bin['matcher'](original, token.kbest(1)[0], self.dictionary, dcode):
				return _bin['heuristic'], dict(_bin)

		Heuristics.log.critical(f'Unable to make decision for token: {token}')
		return 'a', None

	def add_to_report(self, token: Token):
		self.totalCount += 1

		if token.is_punctuation():
			self.punctuationCount += 1
			return

		# strip punctuation, which is considered not relevant to evaluation
		gold = punctuationRE.sub('', token.gold) # gold standard wordform
		orig = punctuationRE.sub('', token.original) # original uncorrected wordform

		# if the token or gold column is empty, a word segmentation error probably occurred in the original
		# (though possibly a deletion)
		# don't count any other errors here; they will be counted in the segmentation error's other line.
		if (token.original == '') & (len(gold) > 0):
			self.undersegmented += 1 # words ran together in original / undersegmentation
			return

		if (token.gold == '') & (len(orig) > 0):
			self.oversegmented += 1 # word wrongly broken apart in original / oversegmentation
			return

		if len(gold) == 0: # after having stripped punctuation the length is 0
			self.nogoldCount += 1

		# total number of real tokens - controlled for segmentation errors
		self.tokenCount += 1

		# k best candidate words
		kbws = [punctuationRE.sub('', candidate) for (k, (candidate,p)) in token.kbest()]

		# best candidate
		k1 = kbws[0]

		# number of distinct k-best words that pass the dictionary check
		nkdict = len(set([kww for kww in kbws if kww in self.dictionary]))

		# filtered words - only candidates that pass dict check
		d1 = None
		if 0 < nkdict < len(kbws):
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

		counts = self.bins[_bin['number']]['counts']

		counts['total'] += 1

		if orig == gold:
			counts['orig == gold'] += 1
		else:
			counts['orig != gold'] += 1

		if k1 == gold:
			counts['k1 == gold'] += 1
		else:
			counts['k1 != gold'] += 1

		if d1 == gold:
			counts['d1 == gold'] += 1
		else:
			counts['d1 != gold'] += 1

	def report(self) -> str:
		Heuristics.log.debug(f'{[(i, b["counts"]) for i,b in self.bins.items()]}')

		out = ''

		out += f'Total tokens included in evaluation: {self.totalCount:10d}         '.rjust(60) + '\n\n'
		out += f'Oversegmented: {self.oversegmented:10d} ({self.oversegmented/self.totalCount:6.2%})'.rjust(60) + '\n'
		out += f'Undersegmented: {self.undersegmented:10d} ({self.undersegmented/self.totalCount:6.2%})'.rjust(60) + '\n'
		out += f'Tokens that are punctuation: {self.punctuationCount:10d} ({self.punctuationCount/self.totalCount:6.2%})'.rjust(60) + '\n'
		out += f'Tokens without gold correction: {self.nogoldCount:10d} ({self.nogoldCount/self.totalCount:6.2%})'.rjust(60) + '\n\n'
		out += f'Tokens available for evaluation: {self.tokenCount:10d} ({self.tokenCount/self.totalCount:6.2%})'.rjust(60) + '\n\n'
		out += 'Choose from these options for each bin:\n'
		out += '\ta (annotator)\n'
		out += '\to (original)\n'
		out += '\tk (k1, best candidate)\n'
		out += '\td (best candidate in dictionary)\n'
		out += '(o and k interchangeable when original is identical to k1; d not applicable in all bins)\n\n\n\n'

		for num in range(1,10):
			out += f'BIN {num} \t\t\t\t\t\t\t\t enter decision here:\t\n'
			out += Heuristics.bins[num]['description'] + '\n'
			total = Heuristics.bins[num]['counts'].pop('total', 0)
			for name, count in Heuristics.bins[num]['counts'].items():
				out += f'tokens where {name}:{count:10d} ({count/self.tokenCount:6.2%})'.rjust(60) + '\n'
			out += f'total:{total:10d} ({total/self.tokenCount:6.2%})'.rjust(60) + '\n'
			out += '\n\n\n'
			Heuristics.bins[num]['counts']['total'] = total

		return out

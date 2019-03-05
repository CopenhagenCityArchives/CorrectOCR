import logging
from collections import OrderedDict, defaultdict
from itertools import islice
from typing import Any, Dict, Tuple

from . import punctuationRE
from .dictionary import Dictionary
from .tokenize import Token


class Heuristics(object):
	log = logging.getLogger(f'{__name__}.Heuristics')

	bins: Dict[int, Dict[str, Any]] = OrderedDict({
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
			'matcher': lambda o, k, d, dcode: o!= k and o not in d and k in d,
			'heuristic': 'a',
		},
		5: {
			'description': 'k1 != original and nothing is in dictionary.',
			'matcher': lambda o, k, d, dcode: o != k and o not in d and dcode == 'zerokd',
			'heuristic': 'a',
		},
		6: {
			'description': 'k1 != original and neither are in dictionary, but a lower-ranked candidate is.',
			'matcher': lambda o, k, d, dcode: o != k and k not in d and o not in d and dcode == 'somekd',
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
		},
		10: {
			'description': 'Catch-all bin, matches any remaining tokens. It is recommended to pass this to annotator.',
			'matcher': lambda o, k, d, dcode: True,
			'heuristic': 'a',
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
			if _bin['matcher'](punctuationRE.sub('', token.original), token.kbest(1)[0], self.dictionary, dcode):
				return _bin['heuristic'], dict(_bin)

		Heuristics.log.critical(f'Unable to make decision for token: {token}')
		return 'a', None

	def add_to_report(self, token: Token):
		self.totalCount += 1

		if token.is_punctuation():
			self.punctuationCount += 1
			return

		# if the token or gold column is empty, a word segmentation error probably occurred in the original
		# (though possibly a deletion)
		# don't count any other errors here; they will be counted in the segmentation error's other half.
		if token.original == '' and len(token.gold) > 0:
			self.undersegmented += 1 # words ran together in original / undersegmentation
			return

		if token.gold == '' and len(token.original) > 0:
			self.oversegmented += 1 # word wrongly broken apart in original / oversegmentation
			return

		if len(token.gold) == 0:
			self.nogoldCount += 1

		# strip punctuation, which is considered not relevant to evaluation
		gold = punctuationRE.sub('', token.gold) # gold standard wordform
		original = punctuationRE.sub('', token.original) # original uncorrected wordform

		# total number of real tokens - controlled for segmentation errors
		self.tokenCount += 1

		# an evidently useful quantity for sorting out what to send to annotators
		#  - can split any existing category across a threshold of this quantity
		#	(based on probabilities of best and 2nd-best candidates)
		# qqh = (token.kbest(1)[1]-token.kbest(2)[1]) / token.kbest(1)[1]

		(_, _bin) = self.evaluate(token)

		if not _bin:
			return # was unable to make heuristic decision

		if 'example' not in Heuristics.bins[_bin['number']] and len(original) > 3:
			Heuristics.bins[_bin['number']]['example'] = token

		if 'counts' not in Heuristics.bins[_bin['number']]:
			Heuristics.bins[_bin['number']]['counts'] = defaultdict(int)
		counts = Heuristics.bins[_bin['number']]['counts']
		counts['total'] += 1

		if original == gold:
			counts['1 gold == orig'] += 1

		if token.kbest(1)[0] == gold:
			counts['2 gold == k1'] += 1

		# lower k best candidate words that pass the dictionary check
		kbest_filtered = [candidate for (k, (candidate,p)) in islice(token.kbest(),1,None) if candidate in self.dictionary]

		if gold in kbest_filtered:
			counts['3 gold == lower kbest'] += 1

	def report(self) -> str:
		Heuristics.log.debug(f'{[(i, b.get("counts", None)) for i,b in self.bins.items()]}')

		out = ''

		out += f'Total tokens included in evaluation: {self.totalCount:10d}         '.rjust(60) + '\n\n'
		out += f'Tokens without gold correction: {self.nogoldCount:10d} ({self.nogoldCount/self.totalCount:6.2%})'.rjust(60) + '\n\n'
		out += f'Oversegmented: {self.oversegmented:10d} ({self.oversegmented/self.totalCount:6.2%})'.rjust(60) + '\n'
		out += f'Undersegmented: {self.undersegmented:10d} ({self.undersegmented/self.totalCount:6.2%})'.rjust(60) + '\n'
		out += f'Tokens that are punctuation: {self.punctuationCount:10d} ({self.punctuationCount/self.totalCount:6.2%})'.rjust(60) + '\n\n'
		out += f'Tokens available for evaluation: {self.tokenCount:10d} ({self.tokenCount/self.totalCount:6.2%})'.rjust(60) + '\n\n'
		out += 'Choose from these options for each bin:\n'
		out += '\ta (annotator)\n'
		out += '\to (original)\n'
		out += '\tk (k1, best candidate)\n'
		out += '\td (best candidate in dictionary)\n'
		out += '(o and k interchangeable when original is identical to k1; d not applicable in all bins)\n\n\n\n'

		for num, _bin in Heuristics.bins.items():
			out += f'BIN {num} \t\t\t\t\t\t\t\t enter decision here:\t\n'
			out += _bin['description'] + '\n'
			if 'counts' in _bin:
				total = _bin['counts'].pop('total', 0)
				for name, count in sorted(_bin['counts'].items(), key=lambda x: x[0]):
					out += f'{name[2:]:20}:{count:10d} ({count/total:6.2%})'.rjust(60) + '\n'
				out += f'total:{total:10d} ({total/self.tokenCount:6.2%})'.rjust(60) + '\n'
				_bin['counts']['total'] = total
			else:
				out += '\tNo tokens matched.'
			if 'example' in _bin:
				example = _bin['example']
				out += f'Example:\n'
				out += f'\toriginal = {example.original}\n'
				out += f'\tgold = {example.gold}\n'
				out += '\tkbest = [\n'
				for k, (candidate, probability) in example.kbest():
					inDict = ' * is in dictionary' if candidate in self.dictionary else ''
					out += f'\t\t{k}: {candidate} ({probability:.2e}){inDict}\n'
				out += '\t]\n'
			out += '\n\n\n'

		return out

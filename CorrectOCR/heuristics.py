from __future__ import annotations

import logging
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass, replace, field
from typing import Callable, DefaultDict, Dict, List, TYPE_CHECKING

import progressbar

from . import punctuationRE
if TYPE_CHECKING:
	from .dictionary import Dictionary
	from .tokens import Token


class Heuristics(object):
	log = logging.getLogger(f'{__name__}.Heuristics')

	@classmethod
	def bin(cls, n: int) -> Bin:
		return _bins[n]._copy()

	def __init__(self, settings: Dict[int, str], dictionary):
		"""
		:param settings: A dictionary of ``bin`` => ``heuristic`` settings.
		:param dictionary: A dictionary for determining correctness of :class:`Tokens<CorrectOCR.tokens.Token>` and suggestions.
		"""
		for (_bin, code) in settings.items():
			_bins[int(_bin)].heuristic = code
		for (number, _bin) in _bins.items():
			_bin.number = number
		Heuristics.log.debug(f'Bins: {_bins}')
		self.dictionary = dictionary
		self.tokenCount = 0
		self.totalCount = 0
		self.punctuationCount = 0
		self.nogoldCount = 0
		self.oversegmented = 0
		self.undersegmented = 0

	def bin_for_token(self, token: 'Token'):
		# k best candidates which are in dictionary
		filtids = [n for n, item in token.kbest.items() if item.normalized in self.dictionary]

		dcode = None
		if len(filtids) == 0:
			dcode = 'zerokd'
		elif 0 < len(filtids) < token.k:
			dcode = 'somekd'
		elif len(filtids) == token.k:
			dcode = 'allkd'

		token_bin = None
		for num, _bin in _bins.items():
			if _bin.matcher(token.normalized, token.kbest[1].normalized, self.dictionary, dcode):
				token_bin = _bin._copy()
				break

		# return decision and chosen candidate(s)
		if token_bin.heuristic == 'o':
			(decision, selection) = ('original', token.original)
		elif token_bin.heuristic == 'k':
			(decision, selection) = ('kbest', 1)
		elif token_bin.heuristic == 'd':
			(decision, selection) = ('kdict', filtids[0])
		else:
			# heuristic is 'a' or unrecognized
			(decision, selection) = ('annotator', filtids)
		
		return decision, selection, token_bin

	def bin_tokens(self, tokens: List['Token'], force = False):
		Heuristics.log.info('Running heuristics on tokens to determine annotator workload.')
		counts = Counter()
		annotatorRequired = 0
		for t in progressbar.progressbar(tokens):
			if force or not t.bin:
				t.decision, t.selection, t.bin = self.bin_for_token(t)
			counts[t.bin.number] += 1
			if t.decision == 'annotator':
				annotatorRequired += 1
		Heuristics.log.debug(f'Counts for each bin: {counts}')
		Heuristics.log.info(f'Annotator required for {annotatorRequired} of {len(tokens)} tokens.')

	def add_to_report(self, token: 'Token'):
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
		# qqh = (token.kbest[1].probablity-token.kbest[2].probability) / token.kbest[1].probability

		(_, _, _bin) = self.bin_for_token(token)

		if not _bin:
			return # was unable to make heuristic decision

		if 'example' not in _bins[_bin.number] and len(original) > 3:
			_bins[_bin.number].example = token

		counts = _bins[_bin.number].counts
		counts['total'] += 1

		if original == gold:
			counts['1 gold == orig'] += 1

		if token.kbest[1].candidate == gold:
			counts['2 gold == k1'] += 1

		# lower k best candidate words that pass the dictionary check
		kbest_filtered = [item.candidate for (k, item) in token.kbest if item.normalized in self.dictionary and k > 1]

		if gold in kbest_filtered:
			counts['3 gold == lower kbest'] += 1

	def report(self) -> str:
		Heuristics.log.debug(f'{[(i, b.counts) for i,b in _bins.items()]}')

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

		for num, _bin in _bins.items():
			out += f'BIN {num} \t\t\t\t\t\t\t\t enter decision here:\t\n'
			out += _bin.description + '\n'
			if 'counts' in _bin:
				total = _bin.counts.pop('total', 0)
				for name, count in sorted(_bin.counts.items(), key=lambda x: x[0]):
					out += f'{name[2:]:20}:{count:10d} ({count/total:6.2%})'.rjust(60) + '\n'
				out += f'total:{total:10d} ({total/self.tokenCount:6.2%})'.rjust(60) + '\n'
				_bin.counts['total'] = total
			else:
				out += '\tNo tokens matched.'
			if 'example' in _bin:
				example = _bin.example
				out += f'Example:\n'
				out += f'\toriginal = {example.original}\n'
				out += f'\tgold = {example.gold}\n'
				out += '\tkbest = [\n'
				for k, item in example.kbest:
					inDict = ' * is in dictionary' if item.normalized in self.dictionary else ''
					out += f'\t\t{k}: {item.candidate} ({item.probability:.2e}){inDict}\n'
				out += '\t]\n'
			out += '\n\n\n'

		return out


##########################################################################################


@dataclass
class Bin:
	"""
	Heuristics bin ...

	TODO TABLE
	"""
	description: str
	"""Description of bin"""
	matcher: Callable[[str, str, Dictionary, str], bool]
	"""Function or lambda which returns `True` if a given :class:`CorrectOCR.tokens.Token` fits into the bin, or `False` otherwise.

	:param o: Original string
	:param k: *k*-best candidate string
	:param d: Dictionary
	:param dcode: One of 'zerokd', 'somekd', 'allkd' for whether zero, some, or all other *k*-best candidates are in dictionary
	"""
	heuristic: str = 'a'
	"""
	Which heuristic the bin is set up for, one of:
	
	-  'a' = Defer to annotator.
	-  'o' = Select original.
	-  'k' = Select top *k*-best.
	-  'd' = Select *k*-best in dictionary.
	"""
	number: int = None #: The number of the bin.
	counts: DefaultDict[str, int] = field(default_factory=lambda: defaultdict(int)) #: Statistics used for reporting.
	example: Token = None #: An example of a matching :class:`CorrectOCR.tokens.Token`, used for reporting.

	def _copy(self):
		return replace(self)


##########################################################################################


_bins: Dict[int, Bin] = OrderedDict({
	1: Bin(
		description='k1 == original and both are in dictionary.',
		matcher=lambda o, k, d, dcode: o == k and o in d,
	),
	2: Bin(
		description='k1 == original but they are not in dictionary, and no other kbest is in dictionary either.',
		matcher=lambda o, k, d, dcode: o == k and o not in d and dcode == 'zerokd',
	),
	3: Bin(
		description='k1 == original but they are not in dictionary, but some lower-ranked kbest is.',
		matcher=lambda o, k, d, dcode: o == k and o not in d and dcode == 'somekd',
	),
	4: Bin(
		description='k1 != original and is in dictionary while original isn''t.',
		matcher=lambda o, k, d, dcode: o != k and o not in d and k in d,
	),
	5: Bin(
		description='k1 != original and nothing is in dictionary.',
		matcher=lambda o, k, d, dcode: o != k and o not in d and dcode == 'zerokd',
	),
	6: Bin(
		description='k1 != original and neither are in dictionary, but a lower-ranked candidate is.',
		matcher=lambda o, k, d, dcode: o != k and k not in d and o not in d and dcode == 'somekd',
	),
	7: Bin(
		description='k1 != original and both are in dictionary.',
		matcher=lambda o, k, d, dcode: o != k and o in d and k in d,
	),
	8: Bin(
		description='k1 != original, original is in dictionary and no candidates are in dictionary.',
		matcher=lambda o, k, d, dcode: o != k and o in d and dcode == 'zerokd',
	),
	9: Bin(
		description='k1 != original, k1 is not in dictionary but both original and a lower candidate are.',
		matcher=lambda o, k, d, dcode: o != k and o in d and k not in d and dcode == 'somekd',
	),
	10: Bin(
		description='Catch-all bin, matches any remaining tokens. It is recommended to pass this to annotator.',
		matcher=lambda o, k, d, dcode: True,
	)
})

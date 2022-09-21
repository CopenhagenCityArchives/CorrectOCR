from __future__ import annotations

import datetime
import logging
import pprint
import traceback
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass, replace, field
from typing import Callable, DefaultDict, Dict, List, TYPE_CHECKING

import progressbar

from ._util import letterRE

if TYPE_CHECKING:
	from .dictionary import Dictionary
	from .tokens import Token
	from .tokens.list import TokenList


_heuristics_map = {
	'a': 'annotator',
	'o': 'original',
	'k': 'kbest',
	'd': 'kdict',
}


class Heuristics(object):
	log = logging.getLogger(f'{__name__}.Heuristics')

	@classmethod
	def bin(cls, n: int) -> Bin:
		return _bins[n]._copy()

	def __init__(self, settings: Dict[int, str], dictionary):
		"""
		:param settings: A dictionary of ``bin number`` => ``heuristic`` settings.
		:param dictionary: A dictionary for determining correctness of :class:`Tokens<CorrectOCR.tokens.Token>` and suggestions.
		"""
		for (_bin, code) in settings.items():
			if code not in _heuristics_map.values():
				Heuristics.log.warning(f'Unknown heuristic for bin {_bin}! Must be one of {_heuristics_map.values()}')
				code = _heuristics_map[code] # attempt to get valid heuristic
			_bins[int(_bin)].heuristic = code
		for (number, _bin) in _bins.items():
			_bin.number = number
		Heuristics.log.debug(f'Bins: {_bins}')
		self.dictionary = dictionary
		self.documents = dict()
		self.tokenCount = 0
		self.totalCount = 0
		self.punctuationCount = 0
		self.hyphenatedCount = 0
		self.malformedTokens = []
		self.nogoldCount = 0
		self.oversegmented = 0
		self.undersegmented = 0
		self.summary = Counter()

	def bin_for_word(self, original, kbest):
		# k best candidates which are in dictionary
		filtids = [n for n, item in kbest.items() if item.candidate in self.dictionary]

		dcode = None
		if len(filtids) == 0:
			dcode = 'zerokd'
		elif 0 < len(filtids) < len(kbest):
			dcode = 'somekd'
		elif len(filtids) == len(kbest):
			dcode = 'allkd'

		token_bin = None
		for num, _bin in _bins.items():
			if _bin.matcher(original, kbest[1].candidate, self.dictionary, dcode):
				token_bin = _bin._copy()
				break

		if token_bin is None:
			raise ValueError(f'No bin matched for: {token}')

		if token_bin.heuristic == 'original':
			selection = original
		elif token_bin.heuristic == 'kbest':
			selection = 1
		elif token_bin.heuristic == 'kdict':
			selection = filtids[0]
		elif token_bin.heuristic == 'annotator':
			selection = filtids
		else:
			raise ValueError(f'Bin {token_bin} has an unknown heuristic: {token_bin.heuristic}')
		
		return token_bin.heuristic, selection, token_bin

	def bin_tokens(self, tokens: TokenList, force = False) -> bool:
		Heuristics.log.info('Running heuristics on tokens to determine annotator workload.')
		modified_count = 0
		counts = Counter()
		annotatorRequired = 0
		ts = iter(tokens)
		for original, gold, token in progressbar.progressbar(tokens.consolidated, max_value=len(tokens)):
			#Heuristics.log.debug(f'binning {token}')
			if force or token.bin is None:
				token.heuristic, token.selection, token.bin = self.bin_for_word(token.original, token.kbest)
				if token.is_hyphenated:
					# ugly...
					next_token = tokens[token.index+1]
					next_token.heuristic = token.heuristic
					next_token.selection = token.selection
					next_token.bin = token.bin
				modified_count += 1
			if token.heuristic is None or token.bin is None or token.selection is None:
				raise ValueError(f'Token {token} was not binned!')
			if token.bin == -1:
				raise ValueError(f'Token {token} was not binned!')
			if token.bin.number == -1:
				raise ValueError(f'Token {token} was not binned!')
			counts[token.bin.number] += 1
			if token.heuristic == 'annotator':
				annotatorRequired += 1
		Heuristics.log.debug(f'Counts for each bin: {counts}')
		Heuristics.log.info(f'Set bin for {modified_count} tokens. Annotator is required for {annotatorRequired} of {len(tokens)} tokens.')
		return modified_count > 0

	def add_to_report(self, tokens, rebin=False, hmm=None):
		if len(tokens) == 0:
			Heuristics.log.warning(f'No tokens were added!')
			return
		self.documents[tokens[0].docid] = len(tokens)
		if rebin:
			Heuristics.log.info(f'Will rebin {len(tokens)} tokens for comparison.')
		for original, gold, token in progressbar.progressbar(tokens.consolidated, max_value=len(tokens)):
			try:
				self.totalCount += 1
				
				if token.is_hyphenated:
					self.hyphenatedCount += 1

				if token.is_punctuation():
					self.punctuationCount += 1
					continue

				# if the token or gold column is empty, a word segmentation error probably occurred in the original
				# (though possibly a deletion)
				# don't count any other errors here; they will be counted in the segmentation error's other half.
				if original == '' and len(gold) > 0:
					self.undersegmented += 1 # words ran together in original / undersegmentation
					continue

				if gold == '' and len(original) > 0:
					self.oversegmented += 1 # word wrongly broken apart in original / oversegmentation
					continue

				if gold is None or len(gold) == 0:
					self.nogoldCount += 1

				# total number of real tokens - controlled for segmentation errors
				self.tokenCount += 1

				# an evidently useful quantity for sorting out what to send to annotators
				#  - can split any existing category across a threshold of this quantity
				#	(based on probabilities of best and 2nd-best candidates)
				# qqh = (token.kbest[1].probablity-token.kbest[2].probability) / token.kbest[1].probability

				if rebin:
					kbest = hmm.kbest_for_word(token.original, token.k)
					heuristic, selection, token_bin = self.bin_for_word(token.original, kbest)
					bin_number = token_bin.number
				else:
					kbest = token.kbest
					bin_number = token.bin.number					

				if _bins[bin_number].example is None and len(original) > 3 and letterRE.search(original):
					_bins[bin_number].example = (original, gold, kbest)

				counts = _bins[bin_number].counts
				counts['total'] += 1

				counts['previous'] = counts.get('previous', defaultdict(int))
				if token.bin and bin_number != token.bin.number:
					counts['previous'][f'bin {token.bin.number}'] += 1
					counts['previous'][f'total'] += 1

				if original == gold:
					counts['(A) gold == orig'] += 1

				if kbest[1].candidate == gold:
					counts['(B) gold == k1'] += 1

				# lower k best candidate words that pass the dictionary check
				kbest_filtered = [item.candidate for (k, item) in kbest.items() if item.candidate in self.dictionary and k > 1]

				if gold in kbest_filtered:
					counts['(C) gold == lower kbest'] += 1

				if token.heuristic:
					counts[f'(D) heuristic was {token.heuristic}'] += 1
				
				if token.heuristic == 'annotator':
					if gold == original:
						counts[f'(E) Annotator accepted the original'] += 1
					elif gold == kbest[1].candidate:
						counts[f'(E) Annotator chose the top candidate'] += 1
					elif any([gold == item.candidate for item in kbest.values()]):
						counts[f'(E) Annotator chose a lower candidate'] += 1
					elif gold is not None:
						counts[f'(E) Annotator made a novel correction'] += 1
			except Exception as e:
				Heuristics.log.error(f'Malformed token: {token}:\n{traceback.format_exc()}')
				self.malformedTokens.append(token)
				continue

	def report(self) -> str:
		if self.totalCount == 0:
			raise ValueError(f'Cannot generate report: No tokens were added!')

		Heuristics.log.debug(f'{[(i, b.counts) for i,b in _bins.items()]}')

		out = f'CorrectOCR Report for {datetime.datetime.now().isoformat()}\n\n'

		out += f'Total documents included in evaluation: {len(self.documents):10d}         '.rjust(60) + '\n\n'
		out += f'Total tokens included in evaluation: {self.totalCount:10d}         '.rjust(60) + '\n\n'
		out += f'Tokens without gold correction: {self.nogoldCount:10d} ({self.nogoldCount/self.totalCount:6.2%})'.rjust(60) + '\n\n'
		out += f'Oversegmented: {self.oversegmented:10d} ({self.oversegmented/self.totalCount:6.2%})'.rjust(60) + '\n'
		out += f'Undersegmented: {self.undersegmented:10d} ({self.undersegmented/self.totalCount:6.2%})'.rjust(60) + '\n'
		out += f'Hyphenated: {self.hyphenatedCount:10d} ({self.hyphenatedCount/self.totalCount:6.2%})'.rjust(60) + '\n'
		out += f'Malformed: {len(self.malformedTokens):10d} ({len(self.malformedTokens)/self.totalCount:6.2%})'.rjust(60) + '\n'
		out += f'Tokens that are punctuation: {self.punctuationCount:10d} ({self.punctuationCount/self.totalCount:6.2%})'.rjust(60) + '\n\n'
		out += f'Tokens available for evaluation: {self.tokenCount:10d} ({self.tokenCount/self.totalCount:6.2%})'.rjust(60) + '\n\n'

		summary = Counter()
		for num, _bin in _bins.items():
			total = _bin.counts.pop('total', 0) if len(_bin.counts) > 0 else 0
			previous = _bin.counts.pop('previous', dict())
			out += f'BIN {num}\t\t {total:10d} tokens ({total/self.tokenCount:6.2%} of total)\n'
			out += _bin.description + '\n'
			out += f'Current heuristic: {_bin.heuristic}\n'
			if len(_bin.counts) > 0:
				for name, count in sorted(_bin.counts.items(), key=lambda x: x[0]):
					out += f'{name:30}: {count:10d}'.rjust(50) + f' ({count/total:6.2%})\n'
					summary[name] += count
			else:
				out += '\tNo tokens matched.\n'
			if len(previous) > 0:
				out += '\nNumber of previously binned tokens that\n'
				out += 'move to this bin with the current model :\n'
				for name, count in sorted(previous.items(), key=lambda x: x[0]):
					out += f'{name:30}: {count:10d}'.rjust(50) + f' ({count/total:6.2%})\n'
			if _bin.example:
				(original, gold, kbest) = _bin.example
				out += f'Example:\n'
				inDict = ' * is in dictionary' if original in self.dictionary else ''
				out += f'\toriginal = {original}{inDict}\n'
				inDict = ' * is in dictionary' if gold is not None and gold in self.dictionary else ''
				out += f'\tgold = {gold}{inDict}\n'
				out += '\tkbest = [\n'
				for k, item in kbest.items():
					inDict = ' * is in dictionary' if item.candidate in self.dictionary else ''
					out += f'\t\t{k}: {item.candidate} ({item.probability:.2e}){inDict}\n'
				out += '\t]\n'
			out += '\n\n\n'

		out += 'Summary of annotations:\n'
		for name, count in sorted(summary.items(), key=lambda x: x[0]):
			out += f'{name:30}: {count:10d}'.rjust(60) + '\n'

		if len(self.malformedTokens) > 0:
			out += f'\n\n\nThere were some malformed tokens:\n\n'
			for token in self.malformedTokens:
				out += f'{pprint.pprint(vars(token))}\n\n'

		out += 'Included documents:\n\t' + '\n\t'.join([f'{docid}: {len(self.documents)} tokens' for docid in sorted(self.documents.keys())]) + '\n'

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
	heuristic: str = 'annotator'
	"""
	Which heuristic the bin is set up for, one of:
	
	-  'annotator' = Defer to annotator.
	-  'original' = Select original.
	-  'kbest' = Select top *k*-best.
	-  'kdict' = Select top *k*-best in dictionary.
	"""
	number: int = None #: The number of the bin.
	counts: DefaultDict[str, int] = field(default_factory=lambda: defaultdict(int)) #: Statistics used for reporting.
	example: (original, gold, kbest) = None #: An example of a match, used for reporting.

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

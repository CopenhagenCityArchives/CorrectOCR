import cmd
import logging
from collections import deque
from typing import List, Iterator, TypeVar, Tuple

from .tokens import TokenList

'''
IMPORTANT BEFORE USING:
To display interactive text your environment must be compatible with the encoding.
For example:
> export LANG=is_IS.UTF-8
> export LC_ALL=is_IS.UTF-8
> locale
> export PYTHONIOENCODING=utf8
'''


T = TypeVar('T')
def _split_window(l: List[T], before=3, after=3) -> Iterator[Tuple[List[T], T, List[T]]]:
	a = deque(maxlen=before)
	for i in range(len(l)):
		yield list(a), l[i], l[i+1:i+1+after]
		a.append(l[i])


class CorrectionShell(cmd.Cmd):
	"""
	Interactive shell for making corrections to a list of tokens. Assumes that the
	tokens are `binned`.
	"""
	log = logging.getLogger(f'{__name__}.CorrectionShell')
	_prompt = 'CorrectOCR> '

	def __init__(self, tokens: TokenList, dictionary, correctionTracking: dict):
		super().__init__()
		self.token = None
		self.heuristic = None
		self.selection = None
		self.tokenwindow = _split_window(tokens, before=7, after=7)
		self.dictionary = dictionary
		self.metrics = {
			'tokenCount': 0,
			'humanCount': 0,
			'tokenTotal': len(tokens),
			'newWords': [],
			'correctionTracking': correctionTracking,
		}
		self.use_rawinput = True

	@classmethod
	def start(cls, tokens: TokenList, dictionary, correctionTracking: dict, intro: str = None):
		"""
		:param tokens: A list of Tokens.
		:param dictionary: A dictionary against which to check validity.
		:param correctionTracking: TODO
		:param intro: Optional introduction text.
		"""
		sh = CorrectionShell(tokens, dictionary, correctionTracking)
		sh.cmdloop(intro)
		return sh.metrics

	def preloop(self):
		return self._nexttoken()

	def _nexttoken(self):
		try:
			while True:  # do-while loop...
				ctxl, self.token, ctxr = next(self.tokenwindow)
				self.metrics['tokenCount'] += 1
				if not self.token.gold:
					break

			if self.token.heuristic == 'annotator':
				self.metrics['humanCount'] += 1 # increment human-effort count
				
				left = ' '.join([c.gold or c.original for c in ctxr])
				right = ' '.join([c.original for c in ctxl])
				print(f'\n\n...{left} \033[1;7m{self.token.original}\033[0m {right}...\n')
				print(f'\nSELECT for {self.token.original} :\n')
				for k, item in self.token.kbest.items():
					inDict = ' * is in dictionary' if item.candidate in self.dictionary else ''
					print(f'\t{k}. {item.candidate} ({item.probability:.2e}){inDict}\n')
				
				self._prompt = f"CorrectOCR {self.metrics['tokenCount']}/{self.metrics['tokenTotal']} ({self.metrics['humanCount']}) > "
			else:
				self.cmdqueue.insert(0, f'{self.token.heuristic} {self.token.selection}')
		except StopIteration:
			print('Reached end of tokens, going to quit...')
			return self.onecmd('quit')
	
	def _select(self, word: str, heuristic: str, save=True):
		print(f'Selecting {heuristic} for "{self.token.original}": "{word}"')
		self.token.gold = word
		if save:
			if word not in self.dictionary:
				self.metrics['newWords'].append(word) # add to suggestions for dictionary review
			self.dictionary.add(word) # add to current dictionary for subsequent heuristics
			if f'{self.token.original}\t{word}' not in self.metrics['correctionTracking']:
				self.metrics['correctionTracking'][f'{self.token.original}\t{word}'] = 0
			self.metrics['correctionTracking'][f'{self.token.original}\t{word}'] += 1
		return self._nexttoken()

	def emptyline(self):
		if self.lastcmd == 'original':
			return super().emptyline() # repeats by default
		else:
			pass # dont repeat other commands

	def do_original(self, _: str):
		"""Choose original (abbreviation: o)"""
		return self._select(self.token.original, 'original')

	def do_shell(self, arg: str):
		"""Custom input to replace token"""
		return self._select(arg, 'user input')

	def do_kbest(self, arg: str):
		"""Choose k-best by number (abbreviation: just the number)"""
		if arg:
			k = int(arg[0]) 
		else:
			k = 1
		return self._select(self.token.kbest[k].candidate, f'{k}-best')

	def do_kdict(self, arg: str):
		"""Choose k-best which is in dictionary"""
		return self._select(self.token.kbest[int(arg)], f'k-best from dict')

	def do_memoized(self, arg: str):
		return self._select(arg, 'memoized correction', save=False)

	def do_error(self, arg: str):
		CorrectionShell.log.error(f'ERROR: {arg} {self.token}')

	def do_linefeed(self, _: str):
		return self._select('\n', 'linefeed', save=False)

	def do_defer(self, _: str):
		"""Defer heuristic for another time."""
		print('Deferring heuristic...')
		return self._nexttoken()

	# noinspection PyMethodMayBeStatic
	def do_quit(self, _: str):
		return True

	def default(self, line: str):
		if line == 'o':
			self.cmdqueue.insert(0, 'original')
		elif line == 'k':
			self.cmdqueue.insert(0, 'kbest 1')
		elif line.isnumeric():
			self.cmdqueue.insert(0, f'kbest {line}')
		elif line == 'd':
			self.cmdqueue.insert(0, 'defer')
		elif line == 'q':
			self.cmdqueue.insert(0, 'quit')
		elif line == 'p':
			print(self.heuristic, self.selection, self.token) # for debugging
		else:
			CorrectionShell.log.error(f'bad command: "{line}"')
			return super().default(line)

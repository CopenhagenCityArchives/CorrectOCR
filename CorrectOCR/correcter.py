import cmd
import logging
from typing import Dict, List

import progressbar

from . import punctuationRE, split_window
from .tokenize import Token

'''
IMPORTANT BEFORE USING:
To display interactive text your environment must be compatible with the encoding.
For example:
> export LANG=is_IS.UTF-8
> export LC_ALL=is_IS.UTF-8
> locale
> export PYTHONIOENCODING=utf8
'''


class Correcter(object):
	log = logging.getLogger(f'{__name__}.Correcter')

	def __init__(self, dictionary, heuristics, memos: Dict[str, str], caseInsensitive=False, k=4):
		self.caseInsensitive = caseInsensitive
		self.memos = memos
		self.k = k
		self.dictionary = dictionary
		self.heuristics = heuristics

	def evaluate(self, token: Token):
		#Correcter.log.debug(token)
		
		# this should not happen in well-formed input
		if len(token.original) == 0:
			return 'error', f'Input is malformed! Original is 0-length: {token}'
		
		# catch linebreaks
		if token.original in [u'_NEWLINE_N_', u'_NEWLINE_R_']:
			return 'linefeed', None
		
		# catch memorised corrections
		if not token.is_punctuation() and token.original in self.memos:
			return 'memoized', self.memos[token.original]
		
		# k best candidate words
		filtids = [k for k, (c,p) in token.kbest() if c in self.dictionary]
		
		(heuristic, token.bin) = self.heuristics.evaluate(token)
		#Correcter.log.debug(f'{bin} {dcode}')
		
		# return decision and output token or candidate list as appropriate
		if heuristic == 'o':
			return 'original', token.original
		elif heuristic == 'k':
			return 'kbest', 1
		elif heuristic == 'd':
			return 'kdict', filtids[0]
		else:
			# heuristic is 'a' or unrecognized
			return 'annotator', filtids

	def bin_tokens(self, tokens: List[Token]):
		Correcter.log.info('Running heuristics on tokens to determine annotator workload.')
		annotatorRequired = 0
		for t in progressbar.progressbar(tokens):
			(t.bin['decision'], t.bin['selection']) = self.evaluate(t)
			if t.bin['decision'] == 'annotator':
				annotatorRequired += 1
		Correcter.log.info(f'Annotator required for {annotatorRequired} of {len(tokens)} tokens.')

		return tokens


class CorrectionShell(cmd.Cmd):
	log = logging.getLogger(f'{__name__}.CorrectionShell')
	prompt = 'CorrectOCR> '

	def __init__(self, tokens: List[Token], dictionary, correctionTracking: dict):
		super().__init__()
		self.token = None
		self.decision = None
		self.selection = None
		self.tokenwindow = split_window(tokens, before=7, after=7)
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
	def start(cls, tokens: List[Token], dictionary, correctionTracking: dict, intro=None):
		sh = CorrectionShell(tokens, dictionary, correctionTracking)
		sh.cmdloop(intro)
		return sh.metrics

	def preloop(self):
		return self.nexttoken()

	def nexttoken(self):
		try:
			ctxl, self.token, ctxr = next(self.tokenwindow)
			if self.token.gold:
				return self.nexttoken()
			(self.decision, self.selection) = (self.token.bin['decision'], self.token.bin['selection'])
			
			self.metrics['tokenCount'] += 1
			if self.decision == 'annotator':
				self.metrics['humanCount'] +=1 # increment human-effort count
				
				left = ' '.join([c.gold or c.original for c in ctxr])
				right = ' '.join([c.original for c in ctxl])
				print(f'\n\n...{left} \033[1;7m{self.token.original}\033[0m {right}...\n')
				print(f'\nSELECT for {self.token.original} :\n')
				for k, (candidate, probability) in self.token.kbest():
					inDict = ' * is in dictionary' if k in self.selection else ''
					print(f'\t{k}. {candidate} ({probability:.2e}){inDict}\n')
				
				self.prompt = f"CorrectOCR {self.metrics['tokenCount']}/{self.metrics['tokenTotal']} ({self.metrics['humanCount']}) > "
			else:
				self.cmdqueue.insert(0, f'{self.decision} {self.selection}')
		except StopIteration:
			print('Reached end of tokens, going to quit...')
			return self.onecmd('quit')
	
	def select(self, word: str, decision: str, save=True):
		print(f'Selecting {decision} for "{self.token.original}": "{word}"')
		self.token.gold = word
		if save:
			cleanword = punctuationRE.sub('', word)
			if cleanword not in self.dictionary:
				self.metrics['newWords'].append(cleanword) # add to suggestions for dictionary review
			self.dictionary.add(cleanword) # add to current dictionary for subsequent heuristic decisions
			if f'{self.token.original}\t{cleanword}' not in self.metrics['correctionTracking']:
				self.metrics['correctionTracking'][f'{self.token.original}\t{cleanword}'] = 0
			self.metrics['correctionTracking'][f'{self.token.original}\t{cleanword}'] += 1
		return self.nexttoken()

	def emptyline(self):
		if self.lastcmd == 'original':
			return super().emptyline() # repeats by default
		else:
			pass # dont repeat other commands

	def do_original(self, arg: str):
		"""Choose original (abbreviation: o)"""
		return self.select(self.token.original, 'original')

	def do_shell(self, arg: str):
		"""Custom input to replace token"""
		return self.select(arg, 'user input')

	def do_kbest(self, arg: str):
		"""Choose k-best by number (abbreviation: just the number)"""
		if arg:
			k = int(arg[0]) 
		else:
			k = 1
		(candidate, _) = self.token.kbest(k)
		return self.select(candidate, f'{k}-best')

	def do_kdict(self, arg: str):
		"""Choose k-best which is in dictionary"""
		(candidate, _) = self.token.kbest(int(arg))
		return self.select(candidate, f'k-best from dict')

	def do_memoized(self, arg: str):
		return self.select(arg, 'memoized correction', save=False)

	def do_error(self, arg: str):
		CorrectionShell.log.error(f'ERROR: {arg} {self.token}')

	def do_linefeed(self, arg: str):
		return self.select('\n', 'linefeed', save=False)

	def do_defer(self, arg: str):
		"""Defer decision for another time."""
		print('Deferring decision...')
		return self.nexttoken()

	def do_quit(self, arg: str):
		return True

	def default(self, line: str):
		if line == 'o':
			return self.onecmd('original')
		elif line == 'k':
			return self.onecmd('kbest 1')
		elif line.isnumeric():
			return self.onecmd(f'kbest {line}')
		elif line == 'q':
			return self.onecmd('quit')
		elif line == 'p':
			print(self.decision, self.selection, self.token) # for debugging
		else:
			CorrectionShell.log.error(f'bad command: "{line}"')
			return super().default(line)

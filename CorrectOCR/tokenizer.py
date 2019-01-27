import csv
import json
import itertools
import logging
from pathlib import Path

import re
import regex
import nltk
import progressbar

from . import open_for_reading
from .dictionary import Dictionary
from .model import HMM, get_alignments


class Token(object):
	def __init__(self, original, gold=None, kbest=[]):
		self.original = original
		self.log = logging.getLogger(__name__+'.Token')
		# Newline characters are kept to recreate the text later,
		# but are replaced by labeled strings for writing to csv.
		if self.original == '\n':
			self.gold = '_NEWLINE_N_',
			self._kbest = [
				('_NEWLINE_N_', 1.0),
				('_NEWLINE_N_', 0.0),
				('_NEWLINE_N_', 0.0),
				('_NEWLINE_N_', 0.0)
			]
		elif self.original == '\r':
			self.gold = '_NEWLINE_R_',
			self._kbest = [
				('_NEWLINE_R_', 1.0),
				('_NEWLINE_R_', 0.0),
				('_NEWLINE_R_', 0.0),
				('_NEWLINE_R_', 0.0)
			]
		elif self.is_punctuation():
			#self.log.debug('{}: is_punctuation'.format(self))
			self.gold = self.original
			self._kbest = []
		else:
			self.gold = gold
			self._kbest = kbest
	
	def __repr__(self):
		#return '<{}>'.format(self.original)
		return '<Token: {}{}{}>'.format(self.original, '/'+self.gold if self.gold else '', ' ({})'.format(self._kbest) if self._kbest else '')
	
	def __eq__(self, other):
		if isinstance(other, self.__class__):
			return self.original.__eq__(other.original)
		elif isinstance(other, str):
			return self.original.__eq__(other)
		else:
			return False
	
	def __lt__(self, other):
		if isinstance(other, self.__class__):
			return self.original.__lt__(other.original)
		elif isinstance(other, str):
			return self.original.__lt__(other)
		else:
			return False
	
	def __hash__(self):
		return self.original.__hash__()
	
	def update(self, other=None, kbest=None, d=None, k=4):
		if other:
			if not self.original: self.original = other.original
			if not self.gold: self.gold = other.gold
			self._kbest = other._kbest
		elif kbest:
			self._kbest = kbest
		elif d:
			original=d['Original']
			gold=d.get('Gold', None)
			kbest = [(d['%d-best'%k], d['%d-best prob.'%k]) for k in range(1, k+1)]
			self.__init__(original, gold, kbest)
	
	def from_dict(d, k=4):
		t = Token('')
		t.update(d=d, k=k)
		return t
	
	def as_dict(self):
		output = {
			'Gold': self.gold or '',
			'Original': self.original,
		}
		for k, (candidate, probability) in enumerate(self._kbest, 1):
			output['%d-best'%k] = candidate
			output['%d-best prob.'%k] = probability
		return output
	
	def kbest(self, k=0):
		if k > 0:
			return self._kbest[k-1]
		else:
			return enumerate(self._kbest, 1)
	
	punctuationRE = regex.compile(r'^\p{punct}+|``$')
	
	def is_punctuation(self):
		return Token.punctuationRE.match(self.original)
	
	def is_numeric(self):
		return self.original.isnumeric()


def tokenize_file(filename, header=0, objectify=True):
	with open_for_reading(filename) as f:
		data = str.join('\n', [l for l in f.readlines()][header:])
	
	words = nltk.tokenize.word_tokenize(data, 'danish')
	
	if not objectify:
		return words
	
	return [Token(w) for w in words]


def tokenize(settings, useExisting=False):
	log = logging.getLogger(__name__+'.tokenize')
	
	tokenFilePath = settings.tokenPath.joinpath(settings.fileid + '_tokens.csv')

	if not settings.force and tokenFilePath.is_file():
		log.info('{} exists and will be returned as Token objects.'.format(tokenFilePath))
		tokens = []
		with open_for_reading(tokenFilePath) as f:
			reader = csv.DictReader(f, delimiter='\t')
			for row in reader:
				tokens.append(Token.from_dict(row, settings.k))
		return tokens
	
	hmm = HMM.fromParamsFile(settings.hmmParamsFile)

	dictionary = Dictionary(settings.dictionaryFile)
	
	# Load previously done tokens if any
	previousTokens = dict()
	if useExisting == True:
		for file in settings.tokenPath.iterdir():
			with open_for_reading(file) as f:
				reader = csv.DictReader(f, delimiter='\t')
				for row in reader:
					previousTokens[row['Original']] = Token.fromDict(row, settings.k)

	multichars = json.load(settings.multiCharacterErrorFile)
	
	(_, wordAlignments, _) = get_alignments(settings.fileid, settings)
	
	log.debug('wordAlignments: {}'.format(wordAlignments))
	
	origfilename = settings.originalPath.joinpath(settings.fileid + '.txt')
	tokens = tokenize_file(origfilename, settings.nheaderlines)
	log.debug('Found {} tokens, first 10: {}'.format(len(tokens), tokens[:10]))
	
	log.info('Generating {} k-best suggestions for each token'.format(settings.k))
	for i, token in enumerate(progressbar.progressbar(tokens)):
		if token in previousTokens:
			token.update(other=previousTokens[token])
		else:
			token.update(kbest=hmm.kbest_for_word(token.original, settings.k, dictionary, multichars))
		if not token.gold and token.original in wordAlignments:
			wa = wordAlignments.get(token.original, dict())
			closest = sorted(wa.items(), key=lambda x: x[0], reverse=True)
			#log.debug('{} {} {}'.format(i, token.original, closest))
			token.gold = closest[0][1]
		previousTokens[token.original] = token
		#log.debug(token.as_dict())
	
	header = ['Original', '1-best', '1-best prob.', '2-best', '2-best prob.', '3-best', '3-best prob.', '4-best', '4-best prob.']
	
	tokenPath = Path(settings.tokenPath).joinpath(settings.fileid + '_tokens.csv')
	with open(tokenPath, 'w', encoding='utf-8') as f:
		log.info('Writing tokens to {}'.format(tokenPath))
		writer = csv.DictWriter(f, header, delimiter='\t', extrasaction='ignore')
		writer.writeheader()
		writer.writerows([t.as_dict() for t in tokens])
	
	goldTokenPath = Path(settings.goldTokenPath).joinpath(settings.fileid + '_goldTokens.csv')
	if len(wordAlignments) > 0:
		with open(goldTokenPath, 'w', encoding='utf-8') as f:
			log.info('Writing tokens to {}'.format(goldTokenPath))
			writer = csv.DictWriter(f, ['Gold']+header, delimiter='\t')
			writer.writeheader()
			writer.writerows([t.as_dict() for t in tokens])
	
	return tokens

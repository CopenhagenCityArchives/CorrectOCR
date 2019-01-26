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
from .model import HMM


class Token(object):
	punctuationRE = regex.compile(r'^\p{posix_punct}+$')
	
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
		else:
			self.gold = gold
			self._kbest = kbest
	
	def update(self, other=None, kbest=None, d=None, k=4):
		if other:
			if not self.original: self.original = other.original
			if not self.gold: self.gold = other.gold
			self._kbest = other._kbest
		elif kbest:
			self._kbest = kbest
		elif d:
			self.original=d['Original']
			self.gold=d.get('Gold', None)
			self._kbest = [(d['%d-best'%k], d['%d-best prob.'%k]) for k in range(1, k+1)]
	
	def from_dict(d, k=4):
		t = Token(None)
		t.update(d, k)
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
	
	def kbest(self, k):
		if k >= len(self._kbest):
			return ('', 0.0)
		else:
			return self._kbest[k-1]
	
	def is_punctuation(self):
		return RE.match(self.original)


def load_text(filename, header=0):
	with open_for_reading(filename) as f:
		data = str.join('\n', [l for l in f.readlines()][header:])
	
	words = nltk.tokenize.word_tokenize(data, 'danish')
	
	return [Token(w) for w in words]


def corrected_words(alignments):
	nonword = re.compile(r'\W+')
	
	log = logging.getLogger(__name__+'.corrected_words')
	
	corrections = dict()
	
	for filename in alignments:
		if not Path(filename).is_file():
			continue
		
		log.info('Getting alignments from {}'.format(filename))
		
		alignments = None
		with open(filename, encoding='utf-8') as f:
			alignments = json.load(f)
	
		pair = ["", ""]
		for a in alignments:
			if nonword.match(a[0]) or nonword.match(a[1]):
				if pair[0] != pair[1]:
					log.debug(pair)
					corrections[pair[0]] = pair[1]
				pair = ["", ""]
			else:
				pair[0] += a[0]
				pair[1] += a[1]
	
	log.debug(corrections)
	
	return corrections


def tokenize(settings, useExisting=False):
	log = logging.getLogger(__name__+'.tokenize')
	
	hmm = HMM.fromParamsFile(settings.hmmParamsFile)

	dictionary = Dictionary(settings.dictionaryFile)
	
	# Load previously done tokens if any
	previousTokens = dict()
	if useExisting == True:
		for file in settings.tokenPath.iterdir():
			with open_for_reading(file) as f:
				reader = csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE, quotechar='')
				for row in reader:
					previousTokens[row['Original']] = Token.fromDict(row, settings.k)

	multichars = json.load(settings.multiCharacterErrorFile)
	
	basename = Path(settings.input_file).stem
	
	header = ['Original', '1-best', '1-best prob.', '2-best', '2-best prob.', '3-best', '3-best prob.', '4-best', '4-best prob.']
	
	corrections = corrected_words([settings.fullAlignmentsPath.joinpath(basename + '_full_alignments.json')])
	
	tokens = load_text(settings.input_file, settings.nheaderlines)
	log.debug('Found {} tokens'.format(len(tokens)))
	
	log.info('Generating {} k-best suggestions for each token'.format(settings.k))
	for token in progressbar.progressbar(tokens):
		if token in previousTokens:
			token.update(other=previousTokens[word])
		else:
			token.update(kbest=hmm.kbest_for_word(token.original, settings.k, dictionary, multichars))
		token.gold = corrections.get(token.original, token.original)
		previousTokens[token.original] = token
		#log.debug(token.as_dict())
	
	tokenPath = Path(settings.tokenPath).joinpath(basename + '_tokens.csv')
	with open(tokenPath, 'w', encoding='utf-8') as f:
		log.info('Writing tokens to {}'.format(tokenPath))
		writer = csv.DictWriter(f, header, delimiter='\t', quoting=csv.QUOTE_NONE, quotechar='', extrasaction='ignore')
		writer.writeheader()
		writer.writerows([t.as_dict() for t in tokens])
	
	goldTokenPath = Path(settings.goldTokenPath).joinpath(basename + '_goldTokens.csv')
	if len(corrections) > 0:
		with open(goldTokenPath, 'w', encoding='utf-8') as f:
			log.info('Writing tokens to {}'.format(goldTokenPath))
			writer = csv.DictWriter(f, ['Gold']+header, delimiter='\t', quoting=csv.QUOTE_NONE, quotechar='')
			writer.writeheader()
			writer.writerows([t.as_dict() for t in tokens])

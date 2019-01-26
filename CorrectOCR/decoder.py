import csv
import json
import regex
import re
import itertools
import logging
from pathlib import Path

from . import open_for_reading
from .dictionary import Dictionary
from .model import HMM


def load_text(filename, header=0):
	f = open_for_reading(filename)
	data = [i for i in f][header:]
	words = []
	temp = []
	controlchars = regex.compile(r'^\p{control}$')
	for line in data:
		for char in line:
			# Keep newline and carriage return, but discard other whitespace
			if char.isspace():
				if char == '\n' or char == '\r':
					if len(temp) > 0:
						words.append(''.join(temp))
					words.append(char)
					temp = []
				else:
					if len(temp) > 0:
						words.append(''.join(temp))
					temp = []
			elif controlchars.match(char):
				pass
			else:
				temp.append(char)
				
	# Add the last word
	if len(temp) > 0:
		words.append(''.join(temp))
				
	return words


def corrected_words(alignments):
	nonword = re.compile(r'\W+')
	
	log = logging.getLogger(__name__+'.corrected_words')
	
	corrections = dict()
	
	for filename in alignments:
		if not Path(filename).is_file():
			continue
		
		log.info('Getting alignments from '.format(filename))
		
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


def decode(settings, use_existing_decodings=False):
	log = logging.getLogger(__name__+'.tokenize')
	
	hmm = HMM.fromParamsFile(settings.hmmParamsFile)

	dictionary = Dictionary(settings.dictionaryFile)
	
	# Load previously done decodings if any
	prev_decodings = dict()
	if use_existing_decodings == True:
		for file in settings.decodedPath.iterdir():
			with open_for_reading(file) as f:
				reader = csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE, quotechar='')
				for row in reader:
					prev_decodings[row['Original']] = row

	words = load_text(settings.input_file, settings.nheaderlines)
	
	# Load multichar file if there is one
	if settings.multiCharacterErrorFile.is_file():
		with open_for_reading(settings.multiCharacterErrorFile) as f:
			multichars = json.load(f)
	else:
		multichars = {}
	
	basename = Path(settings.input_file).stem
	
	header = ['Original', '1-best', '1-best prob.', '2-best', '2-best prob.', '3-best', '3-best prob.', '4-best', '4-best prob.']
	
	corrections = corrected_words([settings.fullAlignmentsPath.joinpath(basename + '_full_alignments.json')])
	
	decoded_words = []
	
	# Newline characters are kept to recreate the text later, but are not passed to the decoder
	# They are replaced by labeled strings for writing to csv
	for word in words:
		if word == '\n':
			decoded_words.append({
				'Gold': '_NEWLINE_N_',
				'Original': '_NEWLINE_N_',
				'1-best': '_NEWLINE_N_', '1-best prob.': 1.0,
				'2-best': '_NEWLINE_N_', '2-best prob.': 0.0,
				'3-best': '_NEWLINE_N_', '3-best prob.': 0.0,
				'4-best': '_NEWLINE_N_', '4-best prob.': 0.0,
			})
		elif word == '\r':
			decoded_words.append({
				'Gold': '_NEWLINE_R_',
				'Original': '_NEWLINE_R_',
				'1-best': '_NEWLINE_R_', '1-best prob.': 1.0,
				'2-best': '_NEWLINE_R_', '2-best prob.': 0.0,
				'3-best': '_NEWLINE_R_', '3-best prob.': 0.0,
				'4-best': '_NEWLINE_R_', '4-best prob.': 0.0,
			})
		else:
			#log.debug('decoding '+word)
			if word in prev_decodings:
				decoded = prev_decodings[word]
			else:
				decoded = hmm.kbest_for_word(word, settings.k, dictionary, multichars)
			#log.debug(decoded)
				prev_decodings[word] = decoded
			if 'Original' not in decoded:
				decoded['Original'] = word
			decoded['Gold'] = corrections.get(decoded['Original'], decoded['Original'])
			decoded_words.append(decoded)
			prev_decodings[word] = decoded
	
	with open(Path(settings.decodedPath).joinpath(basename + '_decoded.csv'), 'w', encoding='utf-8') as f:
		writer = csv.DictWriter(f, header, delimiter='\t', quoting=csv.QUOTE_NONE, quotechar='', extrasaction='ignore')
		writer.writeheader()
		writer.writerows(decoded_words)
	
	if len(corrections) > 0:
		with open(Path(settings.devDecodedPath).joinpath(basename + '_devDecoded.csv'), 'w', encoding='utf-8') as f:
			writer = csv.DictWriter(f, ['Gold']+header, delimiter='\t', quoting=csv.QUOTE_NONE, quotechar='')
			writer.writeheader()
			writer.writerows(decoded_words)

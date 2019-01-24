import csv
import json
import regex
import re
import itertools
import logging
from pathlib import Path

from . import open_for_reading
from .dictionary import Dictionary

class Decoder(object):

	def __init__(self, hmm_path, dict_path=None, prev_decodings=None):
		with open(hmm_path, 'r', encoding='utf-8') as f:
			self.hmm = HMM(*json.load(f, encoding='utf-8'))
		if dict_path:
			self.dictionary = Dictionary(dict_path)
		else:
			self.word_dict = set()
		if prev_decodings is None:
			self.prev_decodings = dict()
		else:
			self.prev_decodings = prev_decodings
	
	def decode_word(self, word, k, multichars={}):
		if len(word) == 0:
			return [''] + ['', 0.0] * k

		if word in self.prev_decodings:
			return self.prev_decodings[word]

		k_best = self.hmm.k_best_beam(word, k)
		# Check for common multi-character errors. If any are present,
		# make substitutions and compare probabilties of decoder results.
		for sub in multichars:
			# Only perform the substitution if none of the k-best decodings are present in the dictionary
			if sub in word and all(self.strip_punctuation(x[0]) not in self.dictionary for x in k_best):
				variant_words = self.multichar_variants(word, sub, multichars[sub])
				for v in variant_words:
					if v != word:
						k_best.extend(self.hmm.k_best_beam(v, k))
				# Keep the k best
				k_best = sorted(k_best, key=lambda x: x[1], reverse=True)[:k]
				   
		k_best = [element for subsequence in k_best for element in subsequence]
		k_best_dict = dict()
		for n in range(0, k):
			k_best_dict['{}-best'.format(n+1)] = k_best[n*2]
			k_best_dict['{}-best prob.'.format(n+1)] = k_best[n*2+1]
		self.prev_decodings[word] = k_best_dict
		
		return k_best_dict
	
	def multichar_variants(self, word, original, replacements):
		variants = [original] + replacements
		variant_words = set()
		pieces = re.split(original, word)
		
		# Reassemble the word using original or replacements
		for x in itertools.product(variants, repeat=word.count(original)):
			variant_words.add(''.join([elem for pair in itertools.izip_longest(
				pieces, x, fillvalue='') for elem in pair]))
			
		return variant_words
	
	def strip_punctuation(self, word):
		# Everything from string.punctuation
		return regex.sub('\p{punct}+', '', word)


class HMM(object):
	
	def __init__(self, initial, transition, emission):
		self.init = initial
		self.tran = transition
		self.emis = emission
		self.logger = logging.getLogger(__name__ + '.HMM')
		
		self.states = initial.keys()
		#self.logger.debug('self.init: ' + str(self.init))
		#self.logger.debug('self.tran: ' + str(self.tran))
		#self.logger.debug('self.emis: ' + str(self.emis))
		#self.logger.debug('self.states: ' + str(self.states))
		#self.symbols = emission[self.states[0]].keys() # Not used ?!
	
	def viterbi(self, char_seq):
		# delta[t][j] is probability of max probability path to state j
		# at time t given the observation sequence up to time t.
		delta = [None] * len(char_seq)
		back_pointers = [None] * len(char_seq)
		
		delta[0] = {i: self.init[i] * self.emis[i][char_seq[0]]
                    for i in self.states}
		
		for t in range(1, len(char_seq)):
			# (preceding state with max probability, value of max probability)
			d = {j: max({i: delta[t-1][i] * self.tran[i][j] for i in self.states}.items(),
                            key=lambda x: x[1]) for j in self.states}
			
			delta[t] = {i: d[i][1] * self.emis[i][char_seq[t]] for i in self.states}
			
			back_pointers[t] = {i: d[i][0] for i in self.states}
		
		best_state = max(delta[-1], key=lambda x: delta[-1][x])
		
		selected_states = [best_state] * len(char_seq)
		for t in range(len(char_seq) - 1, 0, -1):
			best_state = back_pointers[t][best_state]
			selected_states[t-1] = best_state
		
		return ''.join(selected_states)
	
	def k_best_beam(self, word, k):
		# Single symbol input is just initial * emission.
		if len(word) == 1:
			#self.logger.debug('word: '+word)
			paths = [(i, self.init[i] * self.emis[i][word[0]])
                            for i in self.states]
			paths = sorted(paths, key=lambda x: x[1], reverse=True)
		else:
			# Create the N*N sequences for the first two characters
			# of the word.
			paths = [((i, j), (self.init[i] * self.emis[i][word[0]] * self.tran[i][j] * self.emis[j][word[1]]))
                            for i in self.states for j in self.states]
			
			# Keep the k best sequences.
			paths = sorted(paths, key=lambda x: x[1], reverse=True)[:k]
			
			# Continue through the input word, only keeping k sequences at
			# each time step.
			for t in range(2, len(word)):
				temp = [(x[0] + (j,), (x[1] * self.tran[x[0][-1]][j] * self.emis[j][word[t]]))
                                    for j in self.states for x in paths]
				paths = sorted(temp, key=lambda x: x[1], reverse=True)[:k]
				#print(t, len(temp), temp[:5], len(paths), temp[:5])
		
		return [(''.join(seq), prob) for seq, prob in paths[:k]]


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
		
		log.info('Getting alignments from '+filename)
		
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


def decode(settings):
	# - - - Defaults - - -
	# Settings
	use_existing_decodings = True
	
	log = logging.getLogger(__name__+'.decode')
	
	# Load previously done decodings if any
	prev_decodings = dict()
	if use_existing_decodings == True:
		for file in settings.decodedPath.iterdir():
			with open_for_reading(file) as f:
				reader = csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE, quotechar='')
				for row in reader:
					prev_decodings[row['Original']] = row

	# Load the rest of the parameters and create the decoder
	decoder = Decoder(settings.hmmParamsFile, settings.dictionaryFile, prev_decodings)

	words = load_text(settings.input_file, settings.nheaderlines)
	
	# Load multichar file if there is one
	if Path(settings.multiCharacterErrorFile.name).is_file():
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
			decoded = decoder.decode_word(word, settings.k, multichars)
			#log.debug(decoded)
			if 'Original' not in decoded:
				decoded['Original'] = word
			decoded['Gold'] = corrections.get(decoded['Original'], decoded['Original'])
			decoded_words.append(decoded)
	
	with open(Path(settings.decodedPath).joinpath(basename + '_decoded.csv'), 'w', encoding='utf-8') as f:
		writer = csv.DictWriter(f, header, delimiter='\t', quoting=csv.QUOTE_NONE, quotechar='', extrasaction='ignore')
		writer.writeheader()
		writer.writerows(decoded_words)
	
	if len(corrections) > 0:
		with open(Path(settings.devDecodedPath).joinpath(basename + '_devDecoded.csv'), 'w', encoding='utf-8') as f:
			writer = csv.DictWriter(f, ['Gold']+header, delimiter='\t', quoting=csv.QUOTE_NONE, quotechar='')
			writer.writeheader()
			writer.writerows(decoded_words)

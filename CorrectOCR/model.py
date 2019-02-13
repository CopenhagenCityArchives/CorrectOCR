import collections
import itertools
import json
import logging
import re
from collections import defaultdict
from pathlib import Path

from . import punctuationRE, open_for_reading, ensure_new_file
from .tokenize.string import tokenize_file

class HMM(object):
	def __init__(self, initial, transition, emission, multichars={}):
		self.log = logging.getLogger(f'{__name__}.HMM')
		self.init = initial
		self.tran = transition
		self.emis = emission
		self.multichars = multichars
		
		self.states = initial.keys()
		#self.log.debug(f'init: {self.init}')
		#self.log.debug(f'tran: {self.tran}')
		#self.log.debug(f'emis: {self.emis}')
		self.log.debug(f'states: {self.states}')
		
		if not self.parameter_check():
			self.log.critical(f'Parameter check failed for {self}')
		else:
			self.log.debug(f'HMM initialized: {self}')
	
	def __str__(self):
		return f'<{self.__class__.__name__} {"".join(sorted(self.states))}>'
	
	def __repr__(self):
		return self.__str__()

	def save(self, name):
		newname = ensure_new_file(Path(name))
		self.log.info(f'Backed up original HMM parameters to {newname}')
		self.log.info(f'Saving HMM parameters to {name}')
		with open(name, 'w', encoding='utf-8') as f:
			json.dump([self.init, self.tran, self.emis], f)


	def parameter_check(self):
		all_match = True
		if set(self.init) != set(self.tran):
			all_match = False
			self.log.error('Initial keys do not match transition keys.')
		if set(self.init) != set(self.emis):
			all_match = False
			keys = set(self.init).symmetric_difference(set(self.emis))
			self.log.error(
				f'Initial keys do not match emission keys:'
				f' diff: {[k for k in keys]}'
				f' init: {[self.init.get(k, None) for k in keys]}'
				f' emis: {[self.emis.get(k, None) for k in keys]}'
			)
		for key in self.tran:
			if set(self.tran[key]) != set(self.tran):
				all_match = False
				self.log.error(f'Outer transition keys do not match inner keys: {key}')
		if all_match == True:
			self.log.info('Parameters match.')
		return all_match

	def viterbi(self, char_seq): # UNUSED!!
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
		#self.log.debug(f'word: {word}')
		# Single symbol input is just initial * emission.
		if len(word) == 1:
			paths = [(i, self.init[i] * self.emis[i][word[0]])
                            for i in self.states]
			paths = sorted(paths, key=lambda x: x[1], reverse=True)
		else:
			# Create the N*N sequences for the first two characters
			# of the word.
			try:
				paths = [((i, j), (self.init[i] * self.emis[i][word[0]] * self.tran[i][j] * self.emis[j][word[1]]))
								for i in self.states for j in self.states]
			except KeyError as e:
				character = e.args[0]
				self.log.critical(f'[word: {word}] Model is missing character: {character} ({character.encode("utf-8")})')
				raise SystemExit(-1)
			
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
	
	
	def kbest_for_word(self, word, k, dictionary):
		if len(word) == 0:
			return [''] + ['', 0.0] * k

		k_best = self.k_best_beam(word, k)
		# Check for common multi-character errors. If any are present,
		# make substitutions and compare probabilties of results.
		for sub in self.multichars:
			# Only perform the substitution if none of the k-best candidates are present in the dictionary
			if sub in word and all(punctuationRE.sub('', x[0]) not in dictionary for x in k_best):
				variant_words = HMM.multichar_variants(word, sub, self.multichars[sub])
				for v in variant_words:
					if v != word:
						k_best.extend(self.k_best_beam(v, k))
				# Keep the k best
				k_best = sorted(k_best, key=lambda x: x[1], reverse=True)[:k]
		
		return k_best
	
	def multichar_variants(word, original, replacements):
		variants = [original] + replacements
		variant_words = set()
		pieces = re.split(original, word)
		
		# Reassemble the word using original or replacements
		for x in itertools.product(variants, repeat=word.count(original)):
			variant_words.add(''.join([elem for pair in itertools.zip_longest(
				pieces, x, fillvalue='') for elem in pair]))
			
		return variant_words


class HMMBuilder(object):
	# Start with misread counts, remove any keys which are not single
	# characters, remove specified characters, and combine into a single
	# dictionary.
	def generate_confusion(misreadCounts, remove=[]):
		# Outer keys are the correct characters. Inner keys are the counts of
		# what each character was read as.
		confusion = collections.defaultdict(collections.Counter)

		confusion.update(misreadCounts)

		# Strip out any outer keys that aren't a single character
		confusion = {key: value for key, value in confusion.items()
				  if len(key) == 1}

		for unwanted in remove:
			if unwanted in confusion:
				del confusion[unwanted]

		# Strip out any inner keys that aren't a single character.
		# Later, these may be useful, for now, remove them.
		for outer in confusion:
			wrongsize = [key for key in confusion[outer] if len(key) != 1]
			for key in wrongsize:
				del confusion[outer][key]

			for unwanted in remove:
				if unwanted in confusion[outer]:
					del confusion[outer][unwanted]

		#logging.getLogger(f'{__name__}.load_misread_counts').debug(confusion)
		return confusion

	# Get the character counts of the training files. Used for filling in
	# gaps in the confusion probabilities.
	def text_char_counts(files, dictionary, remove=[], nheaderlines=0):
		char_count = collections.Counter()
		for file in files:
			with open_for_reading(file) as f:
				f.readlines(nheaderlines)
				text = f.readlines()
			char_count.update(list(text))

		for word in dictionary:
			char_count.update(list(word))

		for unwanted in remove:
			if unwanted in char_count:
				del char_count[unwanted]

		return char_count

	# Create the emission probabilities using misread counts and character
	# counts. Optionally a file of expected characters can be used to add
	# expected characters as model states whose emission probabilities are set to
	# only output themselves.
	def emission_probabilities(confusion, char_counts, alpha,
							   remove=[], extra_chars=None):
		# Add missing dictionary elements.
		# Missing outer terms are ones which were always read correctly.
		for char in char_counts:
			if char not in confusion:
				confusion[char] = {char: char_counts[char]}
		
		# Inner terms are just added with 0 probability.
		charset = set().union(*[confusion[i].keys() for i in confusion])
		
		for char in confusion:
			for missing in charset:
				if missing not in confusion[char]:
					confusion[char][missing] = 0.0

		# Smooth and convert to probabilities.
		for i in confusion:
			denom = sum(confusion[i].values()) + (alpha * len(confusion[i]))
			for j in confusion[i]:
				confusion[i][j] = (confusion[i][j] + alpha) / denom

		# Add characters that are expected to occur in the texts.
		# Get the characters which aren't already present.
		extra_chars = extra_chars - set(remove)

		# Add them as new states.
		for char in extra_chars:
			if char not in confusion:
				confusion[char] = {i: 0 for i in charset}
		# Add them with 0 probability to every state.
		for i in confusion:
			for char in extra_chars:
				if char not in confusion[i]:
					confusion[i][char] = 0.0
		# Set them to emit themselves
		for char in extra_chars:
			confusion[char][char] = 1.0

		#logging.getLogger(f'{__name__}.emission_probabilities').debug(confusion)
		return confusion

	# Create the initial and transition probabilities from the gold
	# text in the training data.
	def init_tran_probabilities(goldfiles, dictionary, alpha,
								remove=[], nheaderlines=0, extra_chars=None):
		tran = collections.defaultdict(lambda: collections.defaultdict(int))
		init = collections.defaultdict(int)

		def add_word(word):
			if len(word) > 0:
				init[word[0]] += 1
				# Record each occurrence of character pair ij in tran[i][j]
				for i, j in zip(word[0:], word[1:]):
					tran[i][j] += 1

		for file in goldfiles:
			words = tokenize_file(file, header=nheaderlines, objectify=False)
	
			for word in words:
				add_word(word)

		for word in dictionary:
			add_word(word)

		# Create a set of all the characters that have been seen.
		charset = set(tran.keys()) & set(init.keys())
		for key in tran:
			charset.update(set(tran[key].keys()))

		# Add characters that are expected to occur in the texts.
		charset.update(extra_chars)

		for unwanted in remove:
			if unwanted in charset:
				charset.remove(unwanted)
			if unwanted in init:
				del init[unwanted]
			if unwanted in tran:
				del tran[unwanted]
			for i in tran:
				if unwanted in tran[i]:
					del tran[i][unwanted]

		# Add missing characters to the parameter dictionaries and apply smoothing.
		init_denom = sum(init.values()) + (alpha * len(charset))
		for i in charset:
			init[i] = (init[i] + alpha) / init_denom
			tran_denom = sum(tran[i].values()) + (alpha * len(charset))
			for j in charset:
				tran[i][j] = (tran[i][j] + alpha) / tran_denom

		return init, tran

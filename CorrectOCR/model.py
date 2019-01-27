import collections
import json
import logging
import itertools
from difflib import SequenceMatcher
from pathlib import Path
from collections import defaultdict

import regex

from . import open_for_reading
from .dictionary import Dictionary

class Aligner(object):
	def __init__(self, originalPath, correctedPath, fullAlignmentsPath, wordAlignmentsPath, misreadCountsPath):
		self.originalPath = originalPath
		self.correctedPath = correctedPath
		self.fullAlignmentsPath = fullAlignmentsPath
		self.wordAlignmentsPath = wordAlignmentsPath
		self.misreadCountsPath = misreadCountsPath
		self.log = logging.getLogger(__name__+'.align')

	def align_words(self, left, right, index):
		(aPos, bPos, aStr, bStr) = (0, 0, '', '')
		#matcher.set_seq1(best.original)
		m = SequenceMatcher(None, left, right)
		for (a,b,c) in m.get_matching_blocks():
			if a > aPos:
				aStr += left[aPos:a]
			if b > bPos:
				bStr += right[bPos:b]
			if len(aStr) > 0 or len(bStr) > 0:
				self.fullAlignments.append([aStr, bStr])
				self.misreadCounts[aStr][bStr] += 1
			for char in left[a:c]:
				self.fullAlignments.append([char, char])
				self.misreadCounts[char][char] += 1
			(aPos, bPos, aStr, bStr) = (a+c, b+c, '', '')

	def align_tokens(self, left, right, index):
		remove = set()
		
		for i, leftToken in enumerate(left, index):
			matcher = SequenceMatcher(None, None, leftToken.original, autojunk=None)
			(best, bestRatio) = (None, 0.0)
			for rightToken in right:
				matcher.set_seq1(rightToken.original)
				ratio = matcher.ratio()
				if ratio > bestRatio:
					best = rightToken
					bestRatio = ratio
				if ratio == 1.0:
					continue # no reason to compare further
			if best and bestRatio > 0.7 or (len(leftToken.original) > 4 and bestRatio > 0.6):
				#self.log.debug('\t{} -> {} {}'.format(leftToken, best, bestRatio))
				self.align_words(leftToken.original, best.original, i)
				self.wordAlignments[leftToken.original][i] = best.original
				remove.add(leftToken)
			else:
				#self.log.debug('\tbestRatio: {} & {} = {}'.format(leftToken, best, bestRatio))
				pass
		
		return [t for t in left if t not in remove], right

	def alignments(self, fileid, force=False):
		from .tokenizer import tokenize_file
		
		self.fullAlignments = []
		self.wordAlignments = defaultdict(dict)
		self.misreadCounts = collections.defaultdict(collections.Counter)
		
		faPath = self.fullAlignmentsPath.joinpath(fileid + '.json')
		waPath = self.wordAlignmentsPath.joinpath(fileid + '.json')
		mcPath = self.misreadCountsPath.joinpath(fileid + '.json')
		originalFile = self.originalPath.joinpath(fileid + '.txt')
		correctedFile = self.correctedPath.joinpath(fileid + '.txt')
		
		if not force and (faPath.is_file() and waPath.is_file() and mcPath.is_file()):
			# presume correctness, user may clean the files to rerun
			self.log.info('Alignment files exist, will read and return. Use --force og clean files to rerun a subset.')
			return (
				json.load(open_for_reading(faPath)),
				{o: {int(k): v for k,v in i.items()} for o, i in json.load(open_for_reading(waPath)).items()},
				json.load(open_for_reading(mcPath))
			)
		if force:
			self.log.info('Creating alignment files for {}'.format(fileid))
		
		#nopunct = lambda t: not t.is_punctuation()
		#
		#a = list(filter(nopunct, tokenize_file(originalFile)))
		#b = list(filter(nopunct, tokenize_file(goldFile)))
		a = tokenize_file(originalFile)
		b = tokenize_file(goldFile)
		
		matcher = SequenceMatcher(isjunk=lambda t: t.is_punctuation(), autojunk=False)
		matcher.set_seqs(a, b)
		
		leftRest = []
		rightRest = []
		
		for tag, i1, i2, j1, j2 in matcher.get_opcodes():
			if tag == 'equal':
				for token in a[i1:i2]:
					for char in token.original:
						self.fullAlignments.append([char, char])
						self.misreadCounts[char][char] += 1
				self.wordAlignments[token.original][i1] = token.original
			elif tag == 'replace':
				if i2-i1 == j2-j1:
					for leftToken, rightToken in zip(a[i1:i2], b[j1:j2]):
						for leftChar, rightChar in zip(leftToken.original, rightToken.original):
							self.fullAlignments.append([leftChar, rightChar])
							self.misreadCounts[leftChar][rightChar] += 1
						self.wordAlignments[leftToken.original][i1] = rightToken.original
				else:
					#self.log.debug('{:7}   a[{}:{}] --> b[{}:{}] {!r:>8} --> {!r}'.format(tag, i1, i2, j1, j2, a[i1:i2], b[j1:j2]))
					(left, right) = self.align_tokens(a[i1:i2], b[j1:j2], i1)
					leftRest.extend(left)
					rightRest.extend(right)
			elif tag == 'delete':
				leftRest.extend(a[i1:i2])
			elif tag == 'insert':
				rightRest.extend(b[j1:j2])
		
		(left, right) = self.align_tokens(leftRest, rightRest, int(len(a)/3))
		
		#self.log.debug('unmatched tokens left {}: {}'.format(len(left), sorted(left)))
		#self.log.debug('unmatched tokens right {}: {}'.format(len(right), sorted(right)))
	
		with open(faPath, 'w', encoding='utf-8') as f:
			json.dump(self.fullAlignments, f)
			f.close()

		with open(waPath, 'w', encoding='utf-8') as f:
			json.dump(self.wordAlignments, f)
			self.log.debug(self.wordAlignments)
			f.close()
		
		with open(mcPath, 'w', encoding='utf-8') as f:
			json.dump(self.misreadCounts, f)
			f.close()
		
		#self.log.debug('æ: {}'.format(self.misreadCounts['æ']))
		#self.log.debug('cr: {}'.format(self.misreadCounts.get('cr', None)))
		#self.log.debug('c: {}'.format(self.misreadCounts.get('c', None)))
		#self.log.debug('r: {}'.format(self.misreadCounts.get('r', None)))
		
		return (self.fullAlignments, self.wordAlignments, self.misreadCounts)


def align(settings):
	a = Aligner(settings.originalPath, settings.correctedPath, settings.fullAlignmentsPath, settings.wordAlignmentsPath, settings.misreadCountsPath)
	if settings.fileid:
		a.alignments(settings.fileid, force=settings.force)
	elif settings.allPairs:
		for correctedFile in settings.correctedPath.iterdir():
			basename = correctedFile.stem
			a.alignments(basename, force=settings.force)


def get_alignments(fileid, settings, force=False):
	a = Aligner(settings.originalPath, settings.goldPath, settings.fullAlignmentsPath, settings.wordAlignmentsPath, settings.misreadCountsPath)

	return a.alignments(fileid, force=force)


#-------------------------------------

# Load the files of misread counts, remove any keys which are not single
# characters, remove specified characters, and combine into a single
# dictionary.
def load_misread_counts(files, remove=[]):
	# Outer keys are the correct characters. Inner keys are the counts of
	# what each character was read as.
	confusion = collections.defaultdict(collections.Counter)
	for file in files:
		# TODO use get_alignments
		with open_for_reading(file) as f:
			counts = json.load(f, encoding='utf-8')
			for i in counts:
				confusion[i].update(counts[i])

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
	
	#logging.getLogger(__name__+'.load_misread_counts').debug(confusion)
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
	
	#logging.getLogger(__name__+'.emission_probabilities').debug(confusion)
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
	
	from .tokenizer import tokenize_file
	
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


def parameter_check(init, tran, emis):
	log = logging.getLogger(__name__+'.parameter_check')
	all_match = True
	if set(init) != set(tran):
		all_match = False
		log.error('Initial keys do not match transition keys.')
	if set(init) != set(emis):
		all_match = False
		keys = set(init).symmetric_difference(set(emis))
		log.error('Initial keys do not match emission keys: diff: {} init: {} emis: {}'.format([k for k in keys], [init.get(k, None) for k in keys], [emis.get(k, None) for k in keys]))
	for key in tran:
		if set(tran[key]) != set(tran):
			all_match = False
			log.error('Outer transition keys do not match inner keys: {}'.format(key))
	if all_match == True:
		log.info('Parameters match.')
	return all_match


class HMM(object):
	
	def fromParamsFile(path):
		with open_for_reading(path) as f:
			return HMM(*json.load(f, encoding='utf-8'))
	
	def __init__(self, initial, transition, emission):
		self.init = initial
		self.tran = transition
		self.emis = emission
		self.log = logging.getLogger(__name__ + '.HMM')
		self.punctuation = regex.compile(r'\p{posix_punct}+')
		
		self.states = initial.keys()
		self.log.debug('self.init: ' + str(self.init))
		#self.log.debug('self.tran: ' + str(self.tran))
		#self.log.debug('self.emis: ' + str(self.emis))
		self.log.debug('self.states: ' + str(self.states))
		#self.symbols = emission[self.states[0]].keys() # Not used ?!
	
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
		#self.log.debug('word: '+word)
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
				self.log.critical('[word: {}] Model is missing character: {} ({})'.format(word, character, character.encode('utf-8')))
			
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
	
	
	def kbest_for_word(self, word, k, dictionary, multichars={}):
		if len(word) == 0:
			return [''] + ['', 0.0] * k

		k_best = self.k_best_beam(word, k)
		# Check for common multi-character errors. If any are present,
		# make substitutions and compare probabilties of results.
		for sub in multichars:
			# Only perform the substitution if none of the k-best candidates are present in the dictionary
			if sub in word and all(self.punctuation.sub('', x[0]) not in dictionary for x in k_best):
				variant_words = HMM.multichar_variants(word, sub, multichars[sub])
				for v in variant_words:
					if v != word:
						k_best.extend(self.k_best_beam(v, k))
				# Keep the k best
				k_best = sorted(k_best, key=lambda x: x[1], reverse=True)[:k]
		
		return k_best
	
	def multichar_variants(word, original, replacements):
		variants = [original] + replacements
		variant_words = set()
		pieces = regex.split(original, word)
		
		# Reassemble the word using original or replacements
		for x in itertools.product(variants, repeat=word.count(original)):
			variant_words.add(''.join([elem for pair in itertools.zip_longest(
				pieces, x, fillvalue='') for elem in pair]))
			
		return variant_words


#-------------------------------------

def build_model(settings):
	log = logging.getLogger(__name__+'.build_model')
	
	# Settings
	remove_chars = [' ', '\t', '\n', '\r', u'\ufeff', '\x00']

	# Select the gold files which correspond to the misread count files.
	misread_files = []
	gold_files = []
	for file in settings.misreadCountsPath.iterdir():
		misread_files.append(file)
		gold_files.append(settings.goldPath.joinpath(file.stem + '.txt'))
	
	dictionary = Dictionary(settings.dictionaryFile)
	
	confusion = load_misread_counts(misread_files, remove_chars)
	char_counts = text_char_counts(gold_files, dictionary, remove_chars, settings.nheaderlines)

	charset = set(settings.characterSet) | set(char_counts) | set(confusion)

	log.debug(sorted(charset))

	# Create the emission probabilities from the misread counts and the character counts
	emis = emission_probabilities(confusion, char_counts, settings.smoothingParameter, remove_chars,
                               extra_chars=charset)

	# Create the initial and transition probabilities from the gold files
	init, tran = init_tran_probabilities(gold_files, dictionary, settings.smoothingParameter,
                                         remove_chars, settings.nheaderlines, extra_chars=charset)

	if parameter_check(init, tran, emis):
		with open(settings.hmmParamsFile, 'w', encoding='utf-8') as f:
			json.dump((init, tran, emis), f)

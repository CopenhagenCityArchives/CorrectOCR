import collections
import json
import os
import logging

from . import open_for_reading

def align_pairs(settings):
	for pair in settings.filepairs:
		basename = os.path.splitext(os.path.basename(pair[0].name))[0]
		align(settings, basename, pair[0].read(), pair[1].read())

def align(settings, basename, a, b, words=False):
	import difflib
	import collections
	import json
	
	log = logging.getLogger(__name__+'.align')
	
	matcher = difflib.SequenceMatcher(autojunk=False) #isjunk=lambda x: junkre.search(x))
	
	if words:
		a = a.split()
		b = b.split()
	matcher.set_seqs(a, b)
		
	fullAlignments = []
	misreadCounts = collections.defaultdict(collections.Counter)
	misreads = []
	
	for tag, i1, i2, j1, j2 in matcher.get_opcodes():
		if tag != 'equal':
			if max(j2-j1, i2-i1) > 4:							# skip moved lines from overeager contributors :)
				continue
			fullAlignments.append([a[i1:i2], b[j1:j2]])
			misreadCounts[b[j1:j2]][a[i1:i2]] += 1
			misreads.append([b[j1:j2], a[i1:i2], j1, i1])
			log.debug('{:7}   a[{}:{}] --> b[{}:{}] {!r:>8} --> {!r}'.format(tag, i1, i2, j1, j2, a[i1:i2], b[j1:j2]))
		else:
			for char in a[i1:i2]:
				fullAlignments.append([char, char])
				misreadCounts[char][char] += 1
	
	#for char,reads in misreadCounts.copy().items():
	#	if char in reads and len(reads) == 1: # remove characters that were read 100% correctly
	#		del misreadCounts[char]
	
	with open(settings.fullAlignmentsPath + basename + '_full_alignments.json', 'w', encoding='utf-8') as f:
		json.dump(fullAlignments, f)
		f.close()
	
	with open(settings.misreadCountsPath + basename + '_misread_counts.json', 'w', encoding='utf-8') as f:
		json.dump(misreadCounts, f)
		log.debug(misreadCounts)
		f.close()
	
	with open(settings.misreadsPath + basename + '_misreads.json', 'w', encoding='utf-8') as f:
		json.dump(misreads, f)
		f.close()


#-------------------------------------

def load_text(filename, header=0):
	with open_for_reading(filename) as f:
		return [i for i in f][header:]



# Load the files of misread counts, remove any keys which are not single
# characters, remove specified characters, and combine into a single
# dictionary.
def load_misread_counts(file_list, remove=[]):
	# Outer keys are the correct characters. Inner keys are the counts of
	# what each character was read as.
	confusion = collections.defaultdict(collections.Counter)
	for filename in file_list:
		with open(filename, 'r', encoding='utf-8') as f:
			counts = json.load(f, encoding='utf-8')
			for i in counts:
				confusion[i].update(counts[i])

	# Strip out any outer keys that aren't a single character
	confusion = {key:value for key, value in confusion.items()
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
	
	logging.getLogger(__name__+'.load_misread_counts').debug(confusion)
	return confusion

# Get the character counts of the training files. Used for filling in 
# gaps in the confusion probabilities.
def text_char_counts(file_list, remove=[], header=0):
	char_count = collections.Counter()
	for filename in file_list:
		text = load_text(filename, header)
		c = collections.Counter(''.join(text))
		char_count.update(c)

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
			confusion[char] = {char:char_counts[char]}
			
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
	extra_chars = extra_chars.difference(set(confusion))
	extra_chars = extra_chars.difference(set(remove))

	# Add them as new states.				
	for char in extra_chars:
		confusion[char] = {i:0 for i in charset}
	# Add them with 0 probability to every state.
	for i in confusion:
		for char in extra_chars:
			confusion[i][char] = 0.0
	# Set them to emit themselves
	for char in extra_chars:
		confusion[char][char] = 1.0
	
	#logging.getLogger(__name__+'.emission_probabilities').debug(confusion)
	return confusion
	
	
# Create the initial and transition probabilities from the corrected
# text in the training data.
def init_tran_probabilities(file_list, alpha,
							remove=[], header=0, extra_chars=None):
	tran = collections.defaultdict(lambda: collections.defaultdict(int))
	init = collections.defaultdict(int)
	
	for filename in file_list:
		text = load_text(filename, header)

		for line in text:
			for word in line.split():
				if len(word) > 0:
					init[word[0]] += 1
					# Record each occurrence of character pair ij in tran[i][j]
					for i in range(len(word)-1):
						tran[word[i]][word[i+1]] += 1

	# Create a set of all the characters that have been seen.
	charset = set(tran.keys())
	charset.update(set(init.keys()))
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

	# Change the parameter dictionaries into normal dictionaries.
	init = {i:init[i] for i in init}
	tran = {i:{j:tran[i][j] for j in tran[i]} for i in tran}

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
		log.error('Initial keys do not match emission keys:', [k for k in keys], [init.get(k, None) for k in keys], [emis.get(k, None) for k in keys])
	for key in tran:
		if set(tran[key]) != set(tran):
			all_match = False
			log.error('Outer transition keys do not match inner keys: {}'.format(key))
	if all_match == True:
		log.info('Parameters match.')
	return all_match


#-------------------------------------

def build_model(settings):
	# - - - Defaults - - -
	# Settings
	remove_chars = [' ', '\t', '\n', '\r', u'\ufeff', '\x00']

	# Select the gold files which correspond to the misread count files.
	gold_files = []
	misread_files = []
	for filename in os.listdir(settings.hmmTrainPath):
		misread_files.append(os.path.join(settings.hmmTrainPath,filename))
		# [:-10] is to remove '_misread_counts' from the filename
		gold_files.append(os.path.join(settings.correctedPath, 'c_' + os.path.splitext(filename)[0][:-15] + '.txt'))

	confusion = load_misread_counts(misread_files, remove_chars)
	char_counts = text_char_counts(gold_files, remove_chars, settings.nheaderlines)

	# Create the emission probabilities from the misread counts and the character counts
	emis = emission_probabilities(confusion, char_counts, settings.smoothingParameter, remove_chars, 
								  extra_chars=set(list(settings.characterSet)))

	# Create the initial and transition probabilities from the gold files
	init, tran = init_tran_probabilities(gold_files, settings.smoothingParameter,
										 remove_chars, settings.nheaderlines, 
										 extra_chars=set(list(settings.characterSet)))

	if parameter_check(init, tran, emis) == True:
		with open(settings.hmmParamsPath,'w', encoding='utf-8') as f:
			json.dump((init, tran, emis), f)

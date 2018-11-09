import collections
import json
import os



# - - - Defaults - - -
# Settings
num_header_lines = 0
smoothing_parameter = 0.0001
remove_chars = [' ', '\t', '\n', '\r', u'\ufeff', '\x00']

# Inputs
add_chars='train/additional_characters.txt'
sourcedir_hmm = 'train/HMMtrain/'
sourcedir_gold = 'train/parallelSource/'

# Output
hmm_params = 'train/hmm_parameters.txt'

#-------------------------------------

def load_text(filename, header=0):
	try:
		f = open(filename, 'r', encoding='utf-8')
		return [i for i in f][header:]
	except UnicodeDecodeError:
		f = open(filename, 'r', encoding='Windows-1252')
		return [i for i in f][header:]



# Load the files of misread counts, remove any keys which are not single
# characters, remove specified characters, and combine into a single
# dictionary.
def load_misread_counts(file_list, remove=[]):
    # Outer keys are the correct characters. Inner keys are the counts of
    # what each character was read as.
    confusion = collections.defaultdict(collections.Counter)
    for filename in file_list:
        with open(os.path.join(sourcedir_hmm,filename), 'r', encoding='utf-8') as f:
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
	
    print(confusion)
    return confusion

# Get the character counts of the training files. Used for filling in 
# gaps in the confusion probabilities.
def text_char_counts(file_list, remove=[], header=0):
    char_count = collections.Counter()
    for filename in file_list:
        text = load_text(os.path.join(sourcedir_gold, filename), header)
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
                           remove=[], char_file=None):
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
	# Optional per readme.
    if char_file is not None and os.path.exists(char_file):
        with open(char_file, 'r', encoding='utf-8') as f:
            extra_chars = set(list(f.read()))
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
	
    #print(confusion)
    return confusion
    
    
# Create the initial and transition probabilities from the corrected
# text in the training data.
def init_tran_probabilities(file_list, alpha,
                            remove=[], header=0, char_file=None):
    tran = collections.defaultdict(lambda: collections.defaultdict(int))
    init = collections.defaultdict(int)
    
    for filename in file_list:
        text = load_text(os.path.join(sourcedir_gold, filename), header)

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
	# Optional per readme.
    if char_file is not None and os.path.exists(char_file):
        with open(char_file, 'r', encoding='utf-8') as f:
            extra_chars = set(list(f.read()))
        charset.update(set(extra_chars))

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
    all_match = True
    if set(init) != set(tran):
        all_match = False
        print('Initial keys do not match transition keys.')
    if set(init) != set(emis):
        all_match = False
        keys = set(init).symmetric_difference(set(emis))
        print('Initial keys do not match emission keys:', [k.encode('utf-8') for k in keys], [init.get(k, None) for k in keys], [emis.get(k, None) for k in keys])
    for key in tran:
        if set(tran[key]) != set(tran):
            all_match = False
            print('Outer transition keys do not match inner keys: {}'.format(key))
    if all_match == True:
        print('Parameters match.')
    return all_match


#-------------------------------------

# Select the gold files which correspond to the misread count files.
gold_files = []
misread_files = []
for filename in os.listdir(sourcedir_hmm):
    misread_files.append(filename)
    # [:-10] is to remove '_misread_counts' from the filename
    gold_files.append('c_' + os.path.splitext(filename)[0][:-15] + '.txt')

confusion = load_misread_counts(misread_files, remove_chars)
char_counts = text_char_counts(gold_files, remove_chars, num_header_lines)

# Create the emission probabilities from the misread counts and the character counts
emis = emission_probabilities(confusion, char_counts, smoothing_parameter, remove_chars, 
                              char_file=add_chars)

# Create the initial and transition probabilities from the gold files
init, tran = init_tran_probabilities(gold_files, smoothing_parameter,
                                     remove_chars, num_header_lines, 
                                     char_file=add_chars)

if parameter_check(init, tran, emis) == True:
    with open(hmm_params,'w', encoding='utf-8') as f:
        json.dump((init, tran, emis), f)

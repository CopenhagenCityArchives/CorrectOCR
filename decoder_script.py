import argparse
import csv
import json
import os

import decoder



# - - - Defaults - - -
# Settings
num_header_lines = 0
kn = 4
use_existing_decodings = True

# Inputs
hmm_params = 'train/hmm_parameters.json'
dict_file = 'resources/dictionary.txt'
multichar_file = 'resources/multicharacter_errors.txt'

# Output
dir_decodings = 'decoded/'

#-------------------------------------

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dictionary', default=dict_file, help='Dictionary')
    parser.add_argument('input_file', help='text file to decode')

    args = parser.parse_args()

    decoded_words = [['Original']]
    for i in range(kn):
        decoded_words[0].extend(['{}-best'.format(i+1), '{}-best prob.'.format(i+1)])

    # Load previously done decodings if any
    prev_decodings = dict()   
    if use_existing_decodings == True:
        for filename in os.listdir(dir_decodings):
            with open(os.path.join(dir_decodings, filename), 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE, quotechar='')
                for row in reader:
                    prev_decodings[row['Original']] = list(row.values())

    # Load the rest of the parameters and create the decoder
    dec = decoder.Decoder(hmm_params,
                          args.dictionary,
                          prev_decodings)

    words = decoder.load_text(args.input_file, num_header_lines)
    
    # Load multichar file if there is one
    if multichar_file is not None and os.path.exists(multichar_file):
        with open(multichar_file, 'r', encoding='utf-8') as f:
            multichars = json.load(f)
    else:
        multichars = {}

    # Newline characters are kept to recreate the text later, but are not passed to the decoder
    # They are replaced by labeled strings for writing to csv
    for word in words:
        if word == '\n':
            decoded_words.append(['_NEWLINE_N_', '_NEWLINE_N_', 1.0] + ['_NEWLINE_N_', 0.0] * (kn-1))
        elif word == '\r':
            decoded_words.append(['_NEWLINE_R_', '_NEWLINE_R_', 1.0] + ['_NEWLINE_R_', 0.0] * (kn-1))
        else:
            decoded_words.append(dec.decode_word(word, kn, multichars))

    output_file = os.path.splitext(os.path.basename(args.input_file))[0] + '_decoded.csv'


    with open(os.path.join(dir_decodings,output_file), 'w', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter='\t', quoting=csv.QUOTE_NONE, quotechar='')
        writer.writerows(decoded_words)

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
hmm_params = 'train/hmm_parameters.txt'
dict_file = 'resources/dictionary.txt'
multichar_file = 'resources/multicharacter_errors.txt'

# Output
dir_decodings = 'decoded/'

#-------------------------------------

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('input_file', help='text file to decode')

    args = parser.parse_args()

    decoded_words = [['Original']]
    for i in xrange(kn):
        decoded_words[0].extend(['{}-best'.format(i+1), '{}-best prob.'.format(i+1)])

    # Load previously done decodings if any
    prev_decodings = dict()   
    if use_existing_decodings == True:
        for filename in os.listdir(dir_decodings):
            for line in decoder.load_csv_unicode(os.path.join(dir_decodings, filename), '\t', csv.QUOTE_NONE)[1:]:
                prev_decodings[line[0]] = line[1:]

    # Load the rest of the parameters and create the decoder
    dec = decoder.Decoder(decoder.load_hmm(hmm_params),
                          decoder.load_dictionary(dict_file),
                          prev_decodings)

    words = decoder.load_text(args.input_file, num_header_lines)
    
    # Load multichar file if there is one
    if multichar_file != '':
        with open(multichar_file, 'rb') as f:
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


    with open(os.path.join(dir_decodings,output_file), 'wb') as f:
        writer = decoder.UnicodeWriter(f, dialect=csv.excel_tab, quoting=csv.QUOTE_NONE, quotechar=None)
        writer.writerows(decoded_words)

import os
import numpy as np
import timeit
import json
import argparse



# - - - Defaults - - -
# Setting
num_header_lines = 0
output_full_alignment = True

# Outputs
dir_full = 'train/parallelAligned/fullAlignments/'
dir_misread = 'train/parallelAligned/misreads/'
dir_misread_counts = 'train/parallelAligned/misreadCounts/'

#-------------------------------------

def diagonal(n1,n2,pt):
    if(n1 == n2):
        return pt['MATCH']
    else:
        return pt['MISMATCH']


def pointers(di,ho,ve):
    pointer = max(di,ho,ve) #based on python default maximum(return the first element).

    if(di == pointer):
        return 'D'
    elif(ho == pointer):
        return 'H'
    else:
         return 'V'


def load_text(filename, header=0):
    with open(filename, 'rb') as f:
         data = [i.decode('utf-8') for i in f][header:]
    return data


def align(s1, s2, match=1, mismatch=-1, gap=-1, full_output=''):
    penalty = {'MATCH': match, 'MISMATCH': mismatch, 'GAP': gap}  # Penalty dictionary
    n = len(s1) + 1  # # matrix columns
    m = len(s2) + 1  # # matrix rows
    al_mat = np.zeros((m, n), dtype=int)  # Initializes the alignment matrix with zeros
    p_mat = np.zeros((m, n), dtype=str)  # Initializes the alignment matrix with zeros
    # Scans all the first rows element in the matrix and fill it with "gap penalty"
    for i in range(m):
        al_mat[i][0] = penalty['GAP'] * i
        p_mat[i][0] = 'V'
    # Scans all the first columns element in the matrix and fill it with "gap penalty"
    for j in range(n):
        al_mat[0][j] = penalty['GAP'] * j
        p_mat[0][j] = 'H'
    # Fill the matrix with the correct values.

    # Approximation constant to limit and optimize matrix area; assumes a maximum misalignment distance of
    # Ignoring this loop can give a more accurate results, yet computation time will become quadratic
    k = 2*abs(m-n)+20
    for i in range(1, m):
        for j in range(max([i-k,1]), min([i+k, n])):
            al_mat[i][j] = -k

    p_mat[0][0] = 0  # Return the first element of the pointer matrix back to 0.
    for i in range(1, m):
        for j in range(max([i-k,1]), min([i+k, n])):#range(1,n):#
            di = al_mat[i - 1][j - 1] + diagonal(s1[j - 1], s2[i - 1],
                                                 penalty)  # The value for match/mismatch -  diagonal.
            ho = al_mat[i][j - 1] + penalty['GAP']  # The value for gap - horizontal.(from the left cell)
            ve = al_mat[i - 1][j] + penalty['GAP']  # The value for gap - vertical.(from the upper cell)
            al_mat[i][j] = max(di, ho, ve)  # Fill the matrix with the maximal value.(based on the python default maximum)
            p_mat[i][j] = pointers(di, ho, ve)

    #helper indexer functions for word statistics
    def getWordIndex(index):
        a = index
        while a >= 0 and not s1[a].isspace():
            a -= 1
        # Fix a bug occuring when the final character of s1 is whitespace
        if a >= (len(s1) - 1):
            return len(s1) - 1
        return a+1

    def getWordIndex2(index):
        a = index
        # Stuck this in to deal with an edge case
        if a >= len(s2):
            a = len(s2) - 1
        while a >= 0 and not s2[a].isspace():
            a -= 1
        return a+1

    errors = []
    i = n-1
    j = m-1

    
    fullAlign = []
    
    
    while i != 0 and j != 0:
        val = p_mat[j][i]

        if val == 'D' and al_mat[j-1][i-1] <= al_mat[j][i]: # if match
            i -= 1
            j -= 1
            
            fullAlign.append((s1[i], s2[j]))
            
        else: #there is a discrepancy
            correctString = ''
            incorrectString = ''
            while (i != 0 and j != 0) and not (val == 'D' and al_mat[j-1][i-1] <= al_mat[j][i]):
                if val == 'D' and not al_mat[j-1][i-1] <= al_mat[j][i]: #mistmach
                    i -= 1
                    j -= 1
                    correctString = s1[i] + correctString
                    incorrectString = s2[j] + incorrectString
                elif val == 'V':
                    j -= 1
                    incorrectString = s2[j] + incorrectString
                elif val == 'H':
                    i -= 1
                    correctString = s1[i] + correctString
                else:
                    break
                #update value
                val = p_mat[j][i]
            wordIndex = -1
            wordIndex2 = -1
            
            if correctString != ' ': wordIndex = getWordIndex(i)
            if incorrectString != ' ': wordIndex2 = getWordIndex2(j)
            
            errors.append([correctString, incorrectString, wordIndex, wordIndex2])
            
            fullAlign.append((correctString, incorrectString))
            

    if full_output != '':
        fullAlign.reverse()
        with open(full_output, 'wb') as f:
            json.dump(fullAlign, f)
            
    # format: [[correct, incorrect, word index, word index2],...]
    errors.reverse()
    return errors


#-------------------------------------

if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('gold_file', help='corrected version of file')
    parser.add_argument('original_file', help='original version of file')
    
    args = parser.parse_args()
    
    wordCount = 0
    singleErrorWordCount = 0
    multipleErrorWordCount = 0
    charCount = 0
    errorCharCount = 0
    correctCharCountDict = {}
    
    basename = os.path.splitext(os.path.basename(args.original_file))[0]
    print 'Comparing files...'
    print args.original_file, '\n', args.gold_file
    
    #Run
    start = timeit.default_timer()
    
    correctedText = ''.join(load_text(args.gold_file, num_header_lines))
    originalText = ''.join(load_text(args.original_file, num_header_lines))
    
    # Output full alignments or just misread counts and misread indices
    if output_full_alignment == True:
        full_path = os.path.join(dir_full, basename + '_full_alignment.txt')
        newErrors = align(correctedText, originalText, full_output=full_path)
    
    newErrors = align(correctedText, originalText)
    
    # Output the indices of misread characters
    with open(os.path.join(dir_misread, basename + '_misreads.txt'), 'wb') as f:
        json.dump(newErrors, f)
        
    charCount += len(''.join(correctedText.split()))
    errorCharCount += len(newErrors)

    # Get error word counts
    wordCount += len(correctedText.split())
    seen = []
    marked = []

    for _,_,index,_ in newErrors:
        if index == -1: pass
        elif not index in seen:
            seen.append(index)
        elif index in seen and not index in marked:
            marked.append(index)
    multipleErrorWordCount += len(marked)
    singleErrorWordCount += len(seen) - len(marked)
    
    #Get correct char counts
    for char in correctedText:
        if char in correctCharCountDict:
            correctCharCountDict[char] += 1
        else:
            correctCharCountDict[char] = 1

    print 'Characters with error', errorCharCount / float(charCount) * 100 
    print 'Words with one error:', singleErrorWordCount/ float(wordCount) * 100
    print 'Words with multiple errors:', multipleErrorWordCount/ float(wordCount) * 100 
    
    # Count the occurrences of errors, to calculate probabilities later
    misreadCountDictionary = {}
    for char, mistake, _, _ in newErrors:
        if char in misreadCountDictionary:
            if mistake in misreadCountDictionary[char]:
                misreadCountDictionary[char][mistake] += 1
            else:
                misreadCountDictionary[char][mistake] = 1
        else:
            misreadCountDictionary[char] = {mistake : 1}
    
    # Add counts of correct chars to the dictionary
    for char in misreadCountDictionary:
        if len(char) == 1:
            total = sum(misreadCountDictionary[char].values())
            misreadCountDictionary[char][char] = correctCharCountDict[char] - total
    
    # Output the misread counts. These will be used to build the HMM    
    with open(os.path.join(dir_misread_counts, basename + '_misread_counts.txt'), 'wb') as f:
        json.dump(misreadCountDictionary, f)
    
    stop = timeit.default_timer()
    print '\nCompleted in', stop - start, 'seconds.'

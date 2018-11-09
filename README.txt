/-----
/ About
/-----

This is the implementation of an OCR post-processing system as described in 
"Low-resource Post Processing of Noisy OCR Output for Historical Corpus Digitisation"
Caitlin Richter, Matthew Wickes, Deniz Beser and Mitch Marcus, 2018.

Full paper:
http://www.lrec-conf.org/proceedings/lrec2018/pdf/971.pdf


/-----
/ Contact
/-----

¡¡ Please contact us with any issues that come up when using this !!

Caitlin Richter
ricca@seas.upenn.edu

Matthew Wickes
wickesm@seas.upenn.edu


/-----
/Requirements
/-----
Corpus: Plain text documents from moderately bad OCR
Training data: Parallel original/corrected versions for some corpus texts
Dictionary: List of words in the language
Python: 2.7+
Additional packages: NumPy 1.10.4+ (earlier versions may also work)


/-----
/Workflow
/-----
(1) Align parallel texts.
	aligner.py loads the corrected and original versions of a file, forms 
	each into a single string of text, and then aligns them. It produces 
	three different types of output files, all of which use JSON format. 
	These output files are written to the following directories:
	train/parallelAligned/fullAlignments/
		The entire alignment of a corrected and original file
	train/parallelAligned/misreadCounts/
		The counts of characters that were misread by the OCR
	train/parallelAligned/misreads/
		The individual OCR misreads and their indices in the text. 
		Indices are for the entire text files loaded as single strings.
		[[correct, incorrect, correct_index, incorrect_index], ...]
(1a) Create dev set pair files 
	***IN PROGRESS***
	devset_builder.py combines corresponding full alignment files into 
	paired word lists that are used as input to devset_decoder_script.py
	This step may be omitted if paired word lists are already available.
(2) Train HMM decoder on most parallel text.
	model_builder.py loads misread count files from train/HMMtrain/ and 
	loads the corresponding corrected files from train/parallelSource/. The 
	corrected files are used to produce the initial and transition 
	probabilities of the HMM and the misread counts are used to create the 
	emission probabilities. It can additionally be given characters which 
	should or should not be included in the final model.
	The HMM parameters are written to resources/hmm_parameters.txt
(3) Decode texts.
	(3a) decoder_script.py uses the HMM as the base for determining likely 
	  pre-OCR text strings. The HMM only works with 1-to-1 errors, but the 
	  system can be given multicharacter (many-to-1 or 1-to-many) 
	  corrections to try substituting in as well.
	  It can use already decoded files to avoid repeating computations.
	  Output is written to decoded/
	(3b) devset_decoder_script.py creates a dev set for tuning
	  ***IN PROGRESS***
	  Operates in a similar manner to decoder_script.py but the decodings
	  are augmented with known correct forms. 
	  Input files are lists of [correct word, original word]
	  Output is written to train/devDecoded/
(4) Tune correction/annotation decisions on dev set from (3b).
	tune.py uses input from devset_decoder_script.py and outputs report.txt
	User consults report.txt to choose preferred correction & 
	  annotation decisions, and registers these in settings.txt
(5) Correct all non-parallel texts.
	correct.py processes decoded CSVs from (3a) into corrected final texts
	with interactive annotation if settings.txt includes any annotator cases
(6) Optional: Improve performance
	Correction creates more parallel text; iterate train-dev-correct cycles (1-5)
	Correction yields list of potential words to add to dictionary
	Human annotations are tracked; common deterministic ones can 
	  be automated to save annotator time


/-----
/Format & Structure
/-----

- A suggested, default organisation; if you use a different directory setup you will need to specify appropriate paths -

- original -
plain text documents: original (uncorrected) corpus
May have headers with fixed number of lines before body text (default is 0; sample file SAMPLE_1913_SampleSpeaker.txt has 11 lines before body text)

- decoded -
CSVs from original texts decoded to find their candidates for correction
Columns: OriginalToken, k1Candidate, k1Probability, k2Candidate, k2Probability, ...

- corrected -
Finished plain text documents, after correction/annotation of the decoded CSVs.

- train - 
  - additional_characters.txt
  Optional.
  JSON format
  Characters which weren't included in the training data but do occur in the
  corpus. Serves as a simple way of handling very low frequency characters.

  - devAligned -
  ***IN PROGRESS***
  Files for creating dev set. Made from files in parallelAligned/fullAlignments

  - devDecoded -
  CSVs from dev set text decoded to find candidates for correction
  Columns: CorrectToken, OriginalToken, k1Candidate, k1Probability, k2Candidate,
  k2Probability, ...

  - HMMtrain -
  Files for training the HMM. Select them from parallelAligned/misreadCounts/

  - hmm_parameters.txt
  Parameters of the HMM (initial, transition, and emission probabilities)

  - parallelAligned -
    - fullAlignments -
    Entire alignment of corrected and original files. Used to produce dev set
    pair files.
    - misreadCounts -
    Counts of characters being misread by OCR. Source of HMM training files.
    - misreads -
    The individual OCR misreads and their indices. 
    Indices are for the entire text files loaded as single strings.
    [[correct, incorrect, correct_index, incorrect_index], ...]
    Can be used for analyzing error types and context.

  - parallelSource -
  Original and corrected files to be aligned. The corrected files are expected 
  to have a 'c_' prefix.

- resources -
  - dictionary.txt
  Word list, one word per line.
  Can be case-insensitive, or can capitalise words that must always be 
  capitalised.

  - correction_tracking.txt
  Tracks annotator's workload
  Can be ignored if annotator time is not a concern (small corpus) 
  Records every unique (original, correction) pair involving human annotation
  Cumulatively counts occurrences of each pair
  Frequent pairs whose original word is not generally paired with any other 
  correction are deterministic and do not need to be seen by an annotator
  Consider reviewing correction_tracking.txt occasionally to identify such pairs

  - memorised_corrections.txt
  Optional.
  Contains user-specified pairs of (original, correction) forms to bypass rest 
  of correction decision tree.
  Recommended to add pairs identified from correction_tracking.txt
  Can also add pairs to catch systematic mistakes observed in automated 
  decoding/correction.

  - multicharacter_errors.txt
  Optional.
  JSON format
  Contains user-specified types of characters involving multiple characters 
  misread as a single character or single characters misread as multiple 
  characters.
  Example: {'m':['im', 'rn'], 'li':['h']} 

  /newwords
  Contains a list of probable new/out-of-dictionary words generated from 
  correction of each file
  Can be reviewed to enlarge dictionary
  Or merged with dictionary automatically if acceptable quality



//----------------------------------------------------------------//
/-----
/ How to use
/-----

(1) Aligning original and corrected versions of corpus texts
Run aligner.py on each pair of files you want to align.
> python aligner.py path_to_corrected_file path_to_original_file

(1b) Creating dev set pair files 
***IN PROGRESS***

(2) Building the HMM
Put the misread count files of the training set in train/HMMtrain/ and then run
model_builder.py

(3) Decode texts
(3a) Decode original text files
Run decoder_script.py on each original file in the corpus. Any multicharacter 
errors are loaded from multicharacter_errors.txt and the decoder tries them 
when decoding a word.
> python decoder_script.py path_to_original_file

(3b) Decode dev set files
***IN PROGRESS***
Run devset_decoder_script.py on word pair files. Behaves identically to 
decoder.py except for the different input and output files.
> python devset_decoder_script.py path_to_pair_file

(4) Tuning on dev set
* Apply tune.py to the output of devset_decoder_script.py
	optional arguments (if not specified, use defaults)
	d	path to dictionary file
	c	case sensitivity, y/n (default y)
	k	number of candidates decoded per token (default 4)
	v	dev set HMM decodings directory
	o	output file name
> python tune.py -d resources/halfsize_dictionary.txt -o resources/report-halfdict.txt

* Read the output report to choose an action for each of 9 bins
  Available actions:
	a - send token to human Annotator
	o - use Original form
	k - use K1, top-ranked decoding candidate
	d - use the top remaining candidate after filtering for Dictionary membership

ex. in SAMPLE_report.txt:

- nearly 90% of tokens fall into BIN 1.
- of these, the original almost always matches the gold standard
- o is an optimal action: it generates a large amount of correct output (89.2% of all tokens) and leaves only a little error in output (0.3% of all tokens), with no human effort

- 2.8% of tokens fall into BIN 2
- o is reasonable; this would correct 2.2% of tokens and leave .6% as errors
-- alternatively, SAMPLE_report.txt shows a threshold to split the bin & take different actions depending on token being over/under threshold
-- most tokens over threshold are correct as-is (original form is correct; action o)
-- tokens under threshold are harder to sort, and benefit from human annotation (action a)
-- annotating all of BIN 2 (leaving no error) requires annotating 2.8% of the corpus, while annotating only under threshold requires just 1% to be annotated, and leaves only .3% more of corpus tokens as errors.
--!! using thresholds will require editing tune.py and correct.py to implement


* Transcribe choices into settings file
following template of SAMPLE_settings.txt:
	tab-separated
	1st column is bin ID
	2nd column is selection for that bin (o,k,d,a)
or fill in report file with choices (see BINS 1-3 in SAMPLE_report.txt)
  and use makesettings.pys
	required argument input (report) file name
	optional argument	-o output file name 
> python makesettings.py resources/SAMPLE_report.txt -o resources/SAMPLE_settings.txt



(5) Correction
correct.py requires input ID (NOT with a directory path or extension, ex. SAMPLE_1913_SampleSpeaker )
optional arguments:
	d	dictionary file
	v	HMM decodings (CSV) directory
	s	heuristic settings file
	k	number of candidates decoded per token (default 4)
	c	case sensitivity, y/n (default y)
	r	try to repair hyphenated words? y/n (default y)
	o	full path to output file name (default input name prefixed with c_)
	u	output file directory
	w	full path to output file of words to review & add to dictionary
	a	directory to find words to add to dictionary
	t	corrections tracking file
	m	memorised corrections file
	p	plain text original corpus directory
	l	number of lines of metadata before text in original (default 0; 11 for SAMPLE_1913_SampleSpeaker.txt)

> python correct.py SAMPLE_1913_SampleSpeaker

> python correct.py SAMPLE_1913_SampleSpeaker -d resources/halfsize_dictionary.txt -v decoded2 -s resources/SAMPLE_settings.txt -u halfsize-corrections/ -w resources/newwords/SAMPLE_1913_SpSk.txt -l 11


 - - Annotation interface - -

 type digit 1-k: select that # candidate
	- to type these numbers as a token, use escape * (*1, *2, etc)
 o: keep original form & add it to temp dictionary if not already there
 enter key with blank input - same as 'o'
 O: keep original form but NOT add it to temp dictionary

 any other input: replace original token with this input - if no displayed candidates were correct, type in the right word.
	add N to end of typed word to add a newline afterwards
	add A to end of typed word to add it to temp dictionary
	(for both use order NA, ex. " TrøllakamarinumNA "

Any additions to the temp dictionary are in effect for the rest of the current file.

Annotation keys (other than blank input and numbers 1-k) can be redefined for convenience by editing annkey in correct.py

Workflow
--------

Usage of CorrectOCR is divided into several successive tasks.

To train the software, one must first create or obtain set of matching
original uncorrected files with corresponding known-correct “gold”
files. Additionally, a dictionary of the target language is needed.

The pairs of (original, gold) files are then used to train a HMM model
that can then be used to generate *k* replacement candidates for each
token (word) in a new given file. A number of heuristic decisions are
configured based on whether a given token is found in the dictionary,
are the candidates preferable to the original, etc.

Finally, the tokens that could not be corrected based on the heuristics
can be presented to annotators either via CLI or a HTTP server. The annotators'
corrections are then incorporated in a corrected file.

When a corrected file is satisfactory, it can be moved or copied to the
gold directory and in turn be used to tune the HMM further, thus
improving the *k*-best candidates for subsequent files.
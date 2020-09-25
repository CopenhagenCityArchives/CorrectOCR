Commands
--------

Commands and their arguments are called directly on the module, like so:

.. code:: console

   python -m CorrectOCR [command] [args...]

The following commands are available:

-  ``build_dictionary`` creates a dictionary. Input files can be either
   ``.pdf``, ``.txt``, or ``.xml`` (in `TEI
   format <https://en.wikipedia.org/wiki/Text_Encoding_Initiative>`__).
   They may be contained in ``.zip``-files.

   -  The ``--corpusPath`` option specifies a directory of files.
   -  The ``--corpusFile`` option specifies a file containing paths and
      URLs. One such file for a dictionary covering 1800–1948 Danish is
      provided under ``resources/``.
   -  The ``--clear`` option clears the dictionary before adding words
      (the file is backed up first).

   It is strongly recommended to generate a large dictionary for best
   performance.

-  ``align`` aligns a pair of (original, gold) files in order to
   determine which characters and words were misread in the original and
   corrected in the gold.

   -  The ``--fileid`` option specifies a single pair of files to align.
   -  The ``--all`` option aligns all available pairs. Can be combined
      with ``--exclude`` to skip specific files.

-  ``build_model`` uses the alignments to create parameters for the HMM.

   -  The ``--smoothingParameter`` option can be adjusted as needed.

-  ``add`` copies or downloads files to the workspace. One may provide about
   a single file directly, or use the option to provide a list of files.

   -  The ``--documents`` option specifies a file containing paths and
      URLs.
   -  The ``--max_count`` option specifies the maximum number of files
      to add.
   -  The ``--prepare_step`` option allows the automatic preparation of
      the files as they are added. See below.

-  ``prepare`` tokenizes and prepare texts for corrections.

   -  The ``--fileid`` option specifies which file to tokenize.
   -  The ``--all`` option tokenizes all available texts. Can be
      combined with ``--exclude`` to skip specific files.
   -  The ``--step`` option specifies how many of the processing steps
      to take. The default is to take all steps.

      -  ``tokenize`` simply splits the text into tokens (words).
      -  ``align`` aligns tokens with gold versions, if these exist.
      -  ``kbest`` calculates *k*-best correction candidates for each
         token via the HMM.
      -  ``bin`` sorts the tokens into *bins* according to the
         `heuristics <#heuristics>`__ below.

      Each of the steps includes the previous step, and will save
      intermediary information about each token to CSV or a databases.

-  ``stats`` is used to configure which decisions the program should
   make about each bin of tokens:

   -  ``--make_report`` generates a statistical report on whether
      originals/\ *k*-best equal are in the dictionary, etc. This report
      can then be inspected and annotated with the desired decision for
      each *bin*.
   -  ``--make_settings`` creates correction settings based on the
      annotated report.

-  ``correct`` uses the settings to sort the tokens into bins and makes
   automated decisions as configured.

   -  The ``--fileid`` option specifies which file to correct.

   There are three ways to run corrections:

   -  ``--interactive`` runs an interactive correction CLI for the
      remaining undecided tokens (see `Correction
      Interface <#correction-interace>`__ below).
   -  ``--apply`` takes a path argument to an edited token CSV file and
      applies the corrections therein.
   -  ``--autocorrect`` applies available corrections as configured in
      correction settings (ie. any heuristic bins not marked for human
      annotation).

-  ``index`` finds specified terms for use in index-generation.

   -  The ``--fileid`` option specifies a single file for which to
      generate an index.
   -  The ``--all`` option generates indices for all available files.
      Can be combined with ``--exclude`` to skip specific files.
   -  The ``--termFile`` option specifies a text file containing a word
      on each line, which will be matched against the tokens. The option
      may be repeated, and each filename (without extension) will be
      used as markers for the string.
   -  The ``--highlight`` option will create a copy of the input files
      with highlighted words (only available for PDFs).
   -  The ``--autocorrect`` option applies available corrections prior
      to search/highlighting, as above.

-  ``server`` starts a simple Flask backend server that provides ``JSON``
   descriptions and ``.png`` images of tokens, as well as accepts
   ``POST``-requests to update tokens with corrections.

-  ``cleanup`` deletes the backup files in the training directory.

   -  The ``--dryrun`` option simply lists the files without actually
      deleting them.
   -  The ``--full`` option also deletes the current files (ie. those
      without .nnn. in their suffix).
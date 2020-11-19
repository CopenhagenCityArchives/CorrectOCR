CorrectOCR.config module
========================

When invoked, CorrectOCR looks for a file named ``CorrectOCR.ini`` in
the working directory. If found, it is loaded, and any entries will be
considered defaults to their corresponding option. These are the defaults:

.. literalinclude:: ../CorrectOCR/defaults.ini
   :language: ini

By default, CorrectOCR requires 4 subdirectories in the working
directory, which will be used as the current ``Workspace``:

-  ``original/`` contains the original uncorrected files. If necessary,
   it can be configured with the ``--originalPath`` argument.
-  ``gold/`` contains the known correct “gold” files. If necessary, it
   can be configured with the ``--goldPath`` argument.
-  ``training/`` contains the various generated files used during
   training. If necessary, it can be configured with the
   ``--trainingPath`` argument.

Corresponding files in *original* and *gold* are named
identically, and the filename without extension is considered the *file
ID*. The generated files in ``training/`` have suffixes according to
their kind.

If generated files exist, CorrectOCR will generally avoid doing
redundant calculations. The ``--force`` switch overrides this, forcing
CorrectOCR to create new files (after moving the existing ones out of
the way). Alternately, one may delete a subset of the generated files to
only recreate those.

The ``Workspace`` also has a ``ResourceManager`` (accessible in code via
``.resources``) that handles access to the dictionary, HMM parameter
files, etc.

Environment Variables
---------------------

Environment variables follow the format ``CORRECTOCR_<section>_<name>``
in uppercase. For example, the Workspace root path can be configured by
setting ``CORRECTOCR_WORKSPACE_ROOTPATH``.

.. automodule:: CorrectOCR.config
    :members:
    :undoc-members:
    :show-inheritance:


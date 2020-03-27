CorrectOCR
==========

Introduction
------------

CorrectOCR is a tool to post-process OCR text in order to improve its
quality, using a number of methods to minimize annotator work.

Documentation
-------------

Documentation can be found here:

.. image:: https://readthedocs.org/projects/correctocr/badge/?version=latest
   :target: https://correctocr.readthedocs.io/en/latest/?badge=latest
   :alt: Documentation Status

Usage
=====

.. include:: docs/workflow.rst
.. include:: docs/configuration.rst
.. include:: docs/commands.rst
.. include:: docs/heuristics.rst

Correction Interface
--------------------

The annotator will be presented with the tokens that match a heuristic
bin that was marked for annotation.

They may then enter a command. The commands reflect the above settings,
with an additional ``defer`` command to defer decision to a later time.

Prefixing the entered text with an exclamation point causes it to be
considered the corrected version of the token. For example, if the token
is “Wagor” and no suitable candidate is available, the annotator may
enter ``!Wagon`` to correct the word.

Corrections are memoized, so the file need not be corrected fully in one
session. To finish a session and save corrections, use the ``quit``
command.

A ``help`` command is available in the interface.

History
=======

CorrectOCR is based on code created by:

-  Caitlin Richter (ricca@seas.upenn.edu)
-  Matthew Wickes (wickesm@seas.upenn.edu)
-  Deniz Beser (dbeser@seas.upenn.edu)
-  Mitchell Marcus (mitch@cis.upenn.edu)

See their article *“Low-resource Post Processing of Noisy OCR Output for
Historical Corpus Digitisation”* (LREC-2018) for further details, it is
available online:
http://www.lrec-conf.org/proceedings/lrec2018/pdf/971.pdf

The original python 2.7 code (see ``original``-tag in the repository)
has been licensed under Creative Commons Attribution 4.0
(`CC-BY-4.0 <https://creativecommons.org/licenses/by/4.0/>`__, see also
``license.txt`` in the repository).

The code has subsequently been updated to Python 3 and further expanded
by Mikkel Eide Eriksen (mikkel.eriksen@gmail.com) for the `Copenhagen
City Archives <https://www.kbharkiv.dk/>`__ (mainly structural changes,
the algorithms are generally preserved as-is). Pull requests welcome!

Requirements
============

-  Python >= 3.6

For package dependencies see `requirements.txt <requirements.txt>`__.
They can be installed using ``pip install -r requirements.txt``

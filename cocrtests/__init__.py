import sys

from unittest.mock import MagicMock

myprogressbar = MagicMock()

def progressbar_mock(iterator, **kwargs):
	for result in iterator:
		yield result

myprogressbar.progressbar = progressbar_mock

sys.modules['progressbar'] = myprogressbar

import logging

logging.disable(logging.WARN)
logging.debug(f'If this text is visible, debug logging is active. Change it in {__file__}')

from .aligner import *
from .dictionary import *
from .document import *
from .heuristics import *
from .hyphenation import *
from .last_modified import *
from .model import *
from .pdf import *
from .server import *
from .token import *


import pathlib

from CorrectOCR.fileio import FileIO

FileIO.cacheRoot = pathlib.Path('/tmp/').joinpath('__COCRCache__')

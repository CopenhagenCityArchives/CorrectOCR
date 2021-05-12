import logging

logging.disable(logging.WARN)
logging.debug(f'If this text is visible, debug logging is active. Change it in {__file__}')

from .aligner import *
from .heuristics import *
from .hyphenation import *
from .last_modified import *
from .model import *
from .pdf import *
from .punctuation import *
from .server import *


import pathlib

from CorrectOCR.fileio import FileIO

FileIO.cacheRoot = pathlib.Path('/tmp/').joinpath('__COCRCache__')

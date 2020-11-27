import logging

logging.disable(logging.WARN)
logging.debug(f'If this text is visible, debug logging is active. Change it in {__file__}')

from .heuristics import *
from .hyphenation import *
from .model import *
from .pdf import *
from .punctuation import *
from .server import *

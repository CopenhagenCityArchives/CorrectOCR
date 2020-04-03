import logging

logging.disable(logging.WARN)
logging.debug(f'If this text is visible, debug logging is active. Change it in {__file__}')

from .hyphenation import *
from .pdf import *
from .server import *

import logging

from typing import Tuple

from ._super import Token, Tokenizer
from ..workspace import CorpusFile


@Token.register
class StringToken(Token):
	log = logging.getLogger(f'{__name__}.StringToken')

	@property
	def token_info(self):
		return self._string

	@property
	def page(self):
		return 0

	@property
	def frame(self):
		return (0, 0, 0, 0)

	def __init__(self, original, docid, index):
		self._string = original
		super().__init__(original, docid, index)

	def extract_image(self, workspace, highlight_word=True, left=300, right=300, top=15, bottom=15, force=False):
		# It doesn't make sense to show an image for a pure text token.
		return None, None

##########################################################################################


@Tokenizer.register(['.txt'])
class StringTokenizer(Tokenizer):
	log = logging.getLogger(f'{__name__}.StringTokenizer')

	def tokenize(self, file: CorpusFile, storageconfig):
		from .list import TokenList

		tokens = file.body.split()
		#StringTokenizer.log.debug(f'tokens: {tokens}')
		tokenlist = TokenList.new(storageconfig, docid=file.id, tokens=[StringToken(w, file.path.stem, i) for i, w in enumerate(tokens)])

		StringTokenizer.log.debug(f'Found {len(tokens)} tokens, first 10: {tokenlist[:10]}')
	
		return tokenlist

	@staticmethod
	def apply(original: CorpusFile, tokens, outfile: CorpusFile, highlight=False):
		spaced = str.join(' ', [token.gold or token.original for token in tokens])
		despaced = spaced.replace('_NEWLINE_N_', '\n').replace(' \n ', '\n')

		outfile.header = original.header.replace(u'Corrected: No', u'Corrected: Yes') 
		outfile.body = despaced
		outfile.save()

	@staticmethod
	def crop_tokens(original, config, tokens, edge_left = None, edge_right = None):
		StringTokenizer.log.debug(f'Cropping unavailable in {__name__}.')
		pass 
import logging

from ._super import Token, Tokenizer, tokenize_str


@Token.register
class StringToken(Token):
	log = logging.getLogger(f'{__name__}.StringToken')

	@property
	def token_info(self):
		return self._string

	def __init__(self, original, **kwargs):
		self._string = original
		super().__init__(original)


##########################################################################################


@Tokenizer.register(['.txt'])
class StringTokenizer(Tokenizer):
	log = logging.getLogger(f'{__name__}.StringTokenizer')

	def tokenize(self, file, force=False):
		tokens = [StringToken(w) for w in tokenize_str(file.body, self.language.name)]
		StringTokenizer.log.debug(f'Found {len(tokens)} tokens, first 10: {tokens[:10]}')
	
		return tokens

	@staticmethod
	def apply(original, tokens, corrected):
		spaced = str.join(' ', [token.gold or token.original for token in tokens])
		despaced = spaced.replace('_NEWLINE_N_', '\n').replace(' \n ', '\n')

		corrected.header = original.header.replace(u'Corrected: No', u'Corrected: Yes') 
		corrected.body = despaced
		corrected.save()

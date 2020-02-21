import logging

from ._super import Token, Tokenizer, tokenize_str
from ..workspace import CorpusFile


@Token.register
class StringToken(Token):
	log = logging.getLogger(f'{__name__}.StringToken')

	@property
	def token_info(self):
		return self._string

	def __init__(self, original, docid, index):
		self._string = original
		super().__init__(original, docid, index)


##########################################################################################


@Tokenizer.register(['.txt'])
class StringTokenizer(Tokenizer):
	log = logging.getLogger(f'{__name__}.StringTokenizer')

	def tokenize(self, file: CorpusFile, storageconfig):
		from .list import TokenList

		tokens = tokenize_str(file.body, self.language.name)
		#StringTokenizer.log.debug(f'tokens: {tokens}')

		if self.dehyphenate:
			dehyphenated = []
			t = iter(tokens)
			for token in t:
				if token[-1] == '-':
					dehyphenated.append(token[:-1] + next(t))
				else:
					dehyphenated.append(token)
			tokens = dehyphenated
		#StringTokenizer.log.debug(f'tokens: {tokens}')

		tokenlist = TokenList.new(storageconfig, docid=file.id, kind='tokens', tokens=[StringToken(w, file.path.stem, i) for i, w in enumerate(tokens)])
		StringTokenizer.log.debug(f'Found {len(tokens)} tokens, first 10: {tokenlist[:10]}')
	
		return tokenlist

	@staticmethod
	def apply(original: CorpusFile, tokens, corrected: CorpusFile):
		spaced = str.join(' ', [token.gold or token.original for token in tokens])
		despaced = spaced.replace('_NEWLINE_N_', '\n').replace(' \n ', '\n')

		corrected.header = original.header.replace(u'Corrected: No', u'Corrected: Yes') 
		corrected.body = despaced
		corrected.save()

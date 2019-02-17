import logging

import progressbar

from ._super import Token, Tokenizer, tokenize_str
from .. import FileAccess


class StringToken(Token):
	log = logging.getLogger(f'{__name__}.StringToken')

	@property
	def original(self):
		return self._string

	@property
	def token_info(self):
		return ''

	def __init__(self, original, **kwargs):
		self._string = original
		super().__init__(**kwargs)


Token.register(StringToken)


def tokenize_file(filename, language='English'):
	data = FileAccess.load(filename)

	return [StringToken(w) for w in tokenize_str(data, language)]


class StringTokenizer(Tokenizer):
	log = logging.getLogger(f'{__name__}.StringTokenizer')

	def tokenize(self, file, force=False):
		tokens = tokenize_file(file, self.language.name)
		StringTokenizer.log.debug(f'Found {len(tokens)} tokens, first 10: {tokens[:10]}')
	
		StringTokenizer.log.info(f'Generating {self.k}-best suggestions for each token')
		for i, token in enumerate(progressbar.progressbar(tokens)):
			if token in self.previousTokens:
				token._string = self.previousTokens[token].original # TODO HACK?
				token.update(other=self.previousTokens[token])
			else:
				token.update(kbest=self.hmm.kbest_for_word(token.original, self.k, self.dictionary))
			if not token.gold and token.original in self.wordAlignments:
				wa = self.wordAlignments.get(token.original, dict())
				closest = sorted(wa.items(), key=lambda x: x[0], reverse=True)
				#StringTokenizer.log.debug(f'{i} {token.original} {closest}')
				token.gold = closest[0][1]
			self.previousTokens[token.original] = token
			#StringTokenizer.log.debug(token.as_dict())

		StringTokenizer.log.debug(f'Generated for {len(tokens)} tokens, first 10: {tokens[:10]}')
		return tokens


Tokenizer.register(StringTokenizer, ['.txt'])
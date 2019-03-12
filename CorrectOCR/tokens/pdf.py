import logging
from typing import List

import fitz
import progressbar

from ._super import Token, Tokenizer


@Token.register
class PDFToken(Token):
	log = logging.getLogger(f'{__name__}.PDFToken')

	@property
	def token_info(self):
		return (self.page_n, self.rect.x0, self.rect.y0, self.rect.x1, self.rect.y1, self.original, self.block_n, self.line_n, self.word_n)

	def __init__(self, info, **kwargs):
		self.page_n = int(info[0])
		self.rect = fitz.Rect(
			float(info[1]),
			float(info[2]),
			float(info[3]),
			float(info[4]),
		)
		self.rect.normalize()
		(self.block_n, self.line_n, self.word_n) = (
			int(info[6]),
			int(info[7]),
			int(info[8]),
		)
		super().__init__(info[5])

	@property
	def ordering(self):
		return (self.page_n, self.block_n, self.line_n, self.word_n)


##########################################################################################


@Tokenizer.register(['.pdf'])
class PDFTokenizer(Tokenizer):
	log = logging.getLogger(f'{__name__}.PDFTokenizer')

	def tokenize(self, file, force=False):
		doc = fitz.open(str(file))

		tokens = []
		for page in progressbar.progressbar(doc):
			tokens += [PDFToken((page.number, ) + tuple(w)) for w in page.getTextWords()]

		PDFTokenizer.log.debug(f'Found {len(tokens)} tokens, first 10: {tokens[:10]}')

		return tokens

	@staticmethod
	def apply(original, tokens: List[PDFToken], corrected):
		pdf_original = fitz.open(str(original))
		pdf_corrected = fitz.open()

		PDFTokenizer.log.info('Copying images from original to corrected PDF')
		for page in pdf_original:
			PDFTokenizer.log.debug(f'(page {page.number})')
			newpage = pdf_corrected.newPage(-1)
			for image_info in page.getImageList():
				xref = image_info[0]
				stream = pdf_original.extractImage(xref)['image']
				newpage.insertImage(page.rect, stream=stream)

		PDFTokenizer.log.info('Inserting tokens in corrected PDF')
		for token in sorted(tokens, key=lambda x: x.ordering):
			page = pdf_corrected[token.ordering[0]]
			word = token.gold or token.original

			# Adjust rectangle to fit word:
			fontfactor = 0.70
			size = token.rect.height * fontfactor
			textwidth = fitz.getTextlength(word, fontsize=size)
			rect = fitz.Rect(token.rect.x0, token.rect.y0, max(token.rect.x1, token.rect.x0+textwidth+1.0), token.rect.y1 + token.rect.height)

			res = page.insertTextbox(rect, f'{word} ', fontsize=size, render_mode=3)
			if res < 0:
				PDFTokenizer.log.warning(
					f'Token was not inserted properly: {word}\n'
					f' -- token.rect: {token.rect}\n'
					f' -- rect: {rect}\n'
					f' -- font size: {size}\n'
					f' -- calc.width: {textwidth} rect.width: {rect.width}\n'
					f' -- rect.height: {rect.height} result: {res}\n'
				)

		PDFTokenizer.log.info(f'Saving corrected PDF to {corrected}')
		pdf_corrected.save(str(corrected))#, garbage=4, deflate=True)

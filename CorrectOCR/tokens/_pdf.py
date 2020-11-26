import logging
import traceback
from pathlib import Path
from typing import List, Tuple

import fitz
import numpy
import progressbar
import plotille
from PIL import Image, ImageDraw

from ._super import Token, Tokenizer
from ..fileio import FileIO

logging.getLogger('PIL').setLevel(logging.INFO) # avoid potential DEBUG-level spam

@Token.register
class PDFToken(Token):
	log = logging.getLogger(f'{__name__}.PDFToken')

	@property
	def token_info(self):
		return self.page_n, self.rect.x0, self.rect.y0, self.rect.x1, self.rect.y1, self.original, self.block_n, self.line_n, self.word_n

	@property
	def page(self):
		return self.token_info[0]

	@property
	def frame(self):
		return (self.token_info[1], self.token_info[2], self.token_info[3], self.token_info[4])

	def __init__(self, token_info, docid, index):
		original = token_info[5]
		super().__init__(original, docid, index)
		self.page_n = int(token_info[0])
		self.rect = fitz.Rect(
			float(token_info[1]),
			float(token_info[2]),
			float(token_info[3]),
			float(token_info[4]),
		)
		self.rect.normalize()
		(self.block_n, self.line_n, self.word_n) = (
			int(token_info[6]),
			int(token_info[7]),
			int(token_info[8]),
		)
		self.cached_image_path = FileIO.cachePath('pdf').joinpath(
			f'{self.docid}-{self.index}.png'
		)

	@property
	def ordering(self):
		return self.page_n, self.block_n, self.line_n, self.word_n

	def extract_image(self, workspace, highlight_word=True, left=300, right=300, top=15, bottom=15, force=False) -> Tuple[Path, Image.Image]:
		if not force and self.cached_image_path.is_file():
			try:
				img = Image.open(str(self.cached_image_path))
				#PDFToken.log.debug(f'{self.cached_image_path}: {img}')
				return self.cached_image_path, img
			except:
				PDFToken.log.error(f'Error with image file, will attempt regeneration.\n{traceback.format_exc()}')
				return self.extract_image(workspace, highlight_word, left, right, top, bottom, force=True)
		xref, pagerect, pix = workspace._cached_page_image(self.docid, self.page_n) # TODO
		xscale = pix.width / pagerect.width
		yscale = pix.height / pagerect.height
		#PDFToken.log.debug(f'extract_image ({self.index}): {tokenrect} {xscale} {yscale}')
		image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
		tokenrect = self.rect.irect * fitz.Matrix(xscale, yscale)
		#PDFToken.log.debug(f'tokenrect ({self.index}): {tokenrect}')
		#PDFToken.log.debug(f'word_image ({self.index}): {image} token {self} filename {self.cached_image_path}')
		if self.is_hyphenated:
			next_token = workspace.docs[self.docid].tokens[self.index+1]
			PDFToken.log.debug(f'Going to create combined image for {self} and {next_token}')
			_, next_token_img = next_token.extract_image(workspace, highlight_word=False, left=0, right=right, top=top, bottom=bottom, force=True)
			#PDFToken.log.debug(f'next_token_img ({self.index}): {next_token_img}')
			centering_offset = int((tokenrect.height - next_token_img.height)/2)
			#PDFToken.log.debug(f'centering_offset: ({tokenrect.height} - {next_token_img.height})/2 = {centering_offset}')
			paste_coords = (tokenrect.x1, tokenrect.y0 + centering_offset)
			#PDFToken.log.debug(f'paste_coords ({self.index}): {paste_coords}')
			image.paste(next_token_img, paste_coords)
			tokenrect.x1 += next_token_img.width - left
		croprect = (
			max(0, tokenrect.x0 - left),
			max(0, tokenrect.y0 - top),
			min(pix.width, tokenrect.x1 + right),
			min(pix.height, tokenrect.y1 + bottom),
		)
		#PDFToken.log.debug(f'extract_image ({self.index}): {croprect}')
		if highlight_word:
			draw = ImageDraw.Draw(image)
			draw.rectangle(tokenrect, outline=(255, 0, 0), width=3)
		image = image.crop(croprect)
		image.save(self.cached_image_path)
		return self.cached_image_path, image

	def drop_cached_image(self):
		if self.cached_image_path.is_file():
			self.cached_image_path.unlink()

	@staticmethod
	def register(cls):
		return super().register(cls)


##########################################################################################


@Tokenizer.register(['.pdf'])
class PDFTokenizer(Tokenizer):
	log = logging.getLogger(f'{__name__}.PDFTokenizer')

	def tokenize(self, file: Path, storageconfig):
		from .list import TokenList

		doc = fitz.open(str(file))

		tokens = TokenList.new(storageconfig, docid=file.stem)
		for page in doc:
			PDFTokenizer.log.info(f'Getting tokens from {file.name} page {page.number}')
			for w in progressbar.progressbar(page.getTextWords()):
				token = PDFToken((page.number, ) + tuple(w), file.stem, len(tokens))
				tokens.append(token)

		PDFTokenizer.log.debug(f'Found {len(tokens)} tokens, first 10: {tokens[:10]}')

		return tokens

	@staticmethod
	def apply(original, tokens: List[PDFToken], outfile, highlight=False):
		pdf_original = fitz.open(str(original))
		pdf_corrected = fitz.open()

		PDFTokenizer.log.info('Copying images from original to corrected PDF')
		for page in pdf_original:
			PDFTokenizer.log.debug(f'(page {page.number})')
			newpage = pdf_corrected.newPage(-1, page.rect.width, page.rect.height)
			for image_info in page.getImageList():
				xref = image_info[0]
				stream = pdf_original.extractImage(xref)['image']
				newpage.insertImage(page.rect, stream=stream)

		blue = fitz.utils.getColor('blue')
		red = fitz.utils.getColor('red')

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
				if highlight:
					page.drawRect(rect, color=red)
			elif highlight:
				page.drawRect(rect, color=blue)

		PDFTokenizer.log.info(f'Saving corrected PDF to {outfile}')
		pdf_corrected.save(str(outfile))#, garbage=4, deflate=True)

	@staticmethod
	def crop_tokens(original, config, tokens, edge_left = None, edge_right = None):
		pdf_original = fitz.open(str(original))

		page_filter = lambda t: t.token_info[0] == page.number

		PDFTokenizer.log.info(f'Going to crop {len(tokens)} tokens.')
		for page in pdf_original:
			page_width = page.rect.x1
			filtered_tokens = filter(page_filter, tokens)
			page_tokens = list(filtered_tokens)
			if edge_left is None and edge_right is None:
				edge_left, edge_right = PDFTokenizer.calculate_crop_area(page_tokens, page_width)
			elif edge_left is None:
				edge_left = 0
			elif edge_right is None:
				edge_right = page_width
			PDFTokenizer.crop_tokens_to_edges(page_tokens, edge_left, edge_right)
			
	@staticmethod
	def crop_tokens_to_edges(tokens, edge_left, edge_right):
		PDFTokenizer.log.info(f'Marking tokens outside edges as discarded: {edge_left} -- {edge_right}')	
		discard_count = 0
		for t in tokens:
			if not (t.rect.x1 >= edge_left and t.rect.x0 <= edge_right):
				PDFTokenizer.log.debug(f'Marking token as discarded: {t}')	
				t.is_discarded = True
				discard_count += 1
		PDFTokenizer.log.info(f'Total tokens marked as discarded: {discard_count}')

	@staticmethod
	def calculate_crop_area(tokens, width, tolerance=.1, edge_percentage=20, show_histogram=False):
		PDFTokenizer.log.info(f'Going to calculate crop area for {len(tokens)} tokens')
		x_values = []
		for token in tokens:
			#PDFTokenizer.log.info(f'token.rect: {token.rect}')
			for i in range(int(token.rect.x0), int(token.rect.x1)):
				x_values.append(i)
		
		#PDFTokenizer.log.debug(f'min(x_values): {min(x_values)}')
		#PDFTokenizer.log.debug(f'max(x_values): {max(x_values)}')
		counts, bin_edges = numpy.histogram(x_values, bins=100)
		#PDFTokenizer.log.debug(f'counts: {counts}')
		#PDFTokenizer.log.debug(f'bin_edges: {bin_edges}')
		if show_histogram:
			print(plotille.histogram(x_values, bins=int(max(x_values))))
		
		cutoff = max(counts)*tolerance
		PDFTokenizer.log.info(f'Cutoff set to {max(counts)} * {tolerance} = {cutoff}')

		edge_left, edge_right = 0, max(x_values)+1
		for i, c in enumerate(counts[:edge_percentage]):
			#PDFTokenizer.log.debug(f'{i}: {c} < {cutoff} ? => {edge_left}')
			if c < cutoff:
				edge_left = (width*i)/100
		for i, c in enumerate(counts[-edge_percentage:]):
			#PDFTokenizer.log.debug(f'{i}: {c} < {cutoff} ? => {edge_right}')
			if c < cutoff:
				edge_right = (width*(100-i))/100

		return edge_left, edge_right

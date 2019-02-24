import locale
import logging
import re
from contextlib import contextmanager
from functools import partial
from io import BytesIO
from pathlib import Path
from typing import List

import cv2
import fitz
import numpy as np
import progressbar
from PIL import Image
from lxml import html

from ._super import Token, Tokenizer, TokenSegment
from ..fileio import FileIO


@contextmanager
def c_locale():
	try:
		currlocale = locale.getlocale()
	except ValueError:
		currlocale = ('en_US', 'UTF-8')
	logging.getLogger(f'{__name__}.c_locale').debug(f'Switching to C from {currlocale}')
	locale.setlocale(locale.LC_ALL, "C")
	yield
	logging.getLogger(f'{__name__}.c_locale').debug(f'Switching to {currlocale} from C')
	locale.setlocale(locale.LC_ALL, currlocale)


##########################################################################################


class HOCRToken(Token):
	log = logging.getLogger(f'{__name__}.HOCRToken')
	bbox = re.compile(r'bbox (\d+) (\d+) (\d+) (\d+)')

	@property
	def original(self):
		return self._element.text.strip()

	@property
	def token_info(self):
		return (html.tostring(self._element, encoding='unicode'), self.page)

	def __init__(self, info, **kwargs):
		(element, page) = info
		if isinstance(element, str):
			self._element = html.fromstring(element)
		else:
			self._element = element
		self.page = page
		super().__init__(**kwargs)

	def rect(self):
		# example: title='bbox 77 204 93 234; x_wconf 95'
		m = HOCRToken.bbox.search(self._element.attrib['title'])
		if m:
			return tuple(map(int, list(m.group(1, 2, 3, 4))))
		else:
			return (0, 0, 0, 0)

Token.register(HOCRToken)


##########################################################################################


def local_maximum(thresh, section):
	(left, right) = section
	(height, width) = thresh.shape
	
	mask = np.zeros((1, width), dtype=np.uint8)
	mask[0, left:right] = 1
	
	cols = cv2.reduce(thresh, 0, cv2.REDUCE_SUM, dtype=cv2.CV_32S)
	#log.info(f'shapes: {thresh.shape} {cols.shape}')
	(minVal, maxVal, (_, _), (maxX, maxY)) = cv2.minMaxLoc(cols, mask)
	#log.info(f'{left}:{right} -- {minVal} {minX}:{minY} -- {maxVal} {maxX}:{maxY}')
	
	return maxX


def replace_ids(el, replace, index):
	# replace_ids(doc, re.compile(r'(\w)_1'), index)
	el.attrib['id'] = replace.sub(r'\1_{}'.format(index), el.attrib['id'])
	for sub in el:
		replace_ids(sub, replace, index)


def columnize(image, columncount):
	log = logging.getLogger(f'{__name__}.columnize')

	if columncount != 2:
		log.error(f'Cannot columnize {columncount} columns, only 2')
		raise SystemExit(-1)

	# convert from Pillow:
	image = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)

	(height, width, channels) = image.shape

	#(x, y) = (4, 2)
	#scaleX = int((width / 180) / 7)
	#scaleY = int((height / 80) / 14)

	center = int(width/2)
	sections = [
		(0, int(width*.25)),
		(int(center-width*.25), int(center+width*.25)),
		(int(width-width*.25), width-1)
	]
	log.debug(f'Sections: {sections}')
	log.debug(f'Image size {image.shape}')
	#log.debug(f'Scale: x = {scaleX} y = {scaleY}')

	gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

	(ret, thresh) = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
	
	#kernel = np.ones((y*scaleY, x*scaleX), np.uint8)
	#temp_img = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=3)
	#temp_img = cv2.erode(temp_img, kernel, iterations=1)
	
	maxima = list(map(partial(local_maximum, thresh), sections))
	pairs = list(zip(maxima, maxima[1:]))
	log.debug(f'Pairs: {pairs}')
	for index, (left, right) in enumerate(pairs):
		yield (left, 0, right-left, height)


def tokenize_image(fileid: str, page: int, image: Image, language='Eng', force=False):
	log = logging.getLogger(f'{__name__}.tokenize_image')

	columns = []

	with c_locale():
		# C locale workaround, see:
		# https://github.com/sirfz/tesserocr/issues/165
		# https://github.com/tesseract-ocr/tesseract/issues/1670
		# noinspection PyUnresolvedReferences
		from tesserocr import PyTessBaseAPI
		with PyTessBaseAPI(lang=language) as tesseract:
			tesseract.SetImage(image)

			for index, rect in enumerate(columnize(image, 2)):
				log.info(f'Generating hOCR for column {index} of {fileid} page {page}')

				tesseract.SetRectangle(*rect)

				hocr = tesseract.GetHOCRText(0)

				doc = html.fromstring(hocr)
				elements = doc.xpath("//*[@class='ocrx_word']")

				yield (
					page,
					index,
					rect,
					image,
					hocr,
					[HOCRToken((e, page)) for e in elements if e.text.strip() != '']
				)


##########################################################################################


class HOCRTokenizer(Tokenizer):
	log = logging.getLogger(f'{__name__}.HOCRTokenizer')

	def tokenize(self, file, force=False):
		columns = []
		cachefile = Path('__hocrcache__/').joinpath(f'{file.stem}.cache.json')

		if cachefile.is_file():
			columns = FileIO.load(cachefile)
		else:
			if file.suffix in {'.tiff', '.png'}:
				for page, index, rect, image, hocr, tokens in tokenize_image(file.stem, 0, Image.open(str(file)), self.language.alpha_3):
					columns.append(TokenSegment(
						file.stem,
						page,
						index,
						rect,
						image,
						hocr,
						tokens
					))
			elif file.suffix == '.pdf':
				doc = fitz.open(str(file))
				for pageno in range(1, len(doc)):
					HOCRTokenizer.log.info(f'Extracting images from page {pageno}')
					for image_info in doc.getPageImageList(pageno):
						# [xref, smask, width, height, bpc, colorspace, alt. colorspace, name, filter]
						HOCRTokenizer.log.debug(f'Image info: {image_info}')
						if image_info[1] != 0:
							HOCRTokenizer.log.error('Cannot handle images with smasks')
							raise SystemExit(-1)
						image = doc.extractImage(image_info[0])
						# https://pymupdf.readthedocs.io/en/latest/functions/#Document.extractImage
						HOCRTokenizer.log.debug(f'Image format: {image["ext"]}')
						img = Image.open(BytesIO(image['image']))
						for page, index, rect, image, hocr, tokens in tokenize_image(file.stem, pageno, img, self.language.alpha_3):
							columns.append(TokenSegment(
								file.stem,
								page,
								index,
								rect,
								image,
								hocr,
								tokens
							))
			else:
				HOCRTokenizer.log.error(f'Cannot handle {file}')
				raise SystemExit(-1)

		FileIO.save(columns, cachefile)

		all_tokens = [t for c in columns for t in c.tokens]

		HOCRTokenizer.log.debug(f'Found {len(all_tokens)} tokens, first 10: {all_tokens[:10]}')

		return self.generate_kbest(all_tokens)

	def apply(original, tokens: List[HOCRToken], corrected):
		if original.suffix == '.pdf':
			doc = fitz.open(str(original))
		else:
			doc = fitz.open()
			pix = fitz.Pixmap(str(original))
			page = doc.newPage(-1, width=pix.width, height=pix.height)
			page.insertImage(page.rect, pixmap = pix)

		for token in progressbar.progressbar(tokens):
			(x0, y0, x1, y1) = token.rect()
			HOCRTokenizer.log.debug(f'{token.gold or token.original} -- rect: {x0}, {y0}, {x1}, {y1}')
			rect = fitz.Rect(x0, y0, x1, y1)
			center = fitz.Point((x1-x0)/2,(y1-y0)/2)
			scale = fitz.Matrix(0.5, 0.5)
			doc[token.page].insertTextbox(rect, token.gold or token.original, morph=(center, scale))

		doc.save(str(corrected.parent.joinpath(corrected.stem + '.pdf')))


Tokenizer.register(HOCRTokenizer, ['.pdf', '.tiff', '.png'])

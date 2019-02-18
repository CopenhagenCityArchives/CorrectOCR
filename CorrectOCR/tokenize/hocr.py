import locale
import logging
from contextlib import contextmanager
from functools import partial
from io import BytesIO

import cv2
import fitz
import numpy as np
from lxml import html
from PIL import Image

from ._super import Token, Tokenizer
from .. import FileAccess


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


class HOCRToken(Token):
	log = logging.getLogger(f'{__name__}.HOCRToken')

	@property
	def original(self):
		return self._element.text.strip()

	@property
	def token_info(self):
		return html.tostring(self._element)

	def __init__(self, element, **kwargs):
		if isinstance(element, str):
			self._element = html.fromstring(element)
		else:
			self._element = element
		super().__init__(**kwargs)


Token.register(HOCRToken)


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


class PDFColumn(object):
	log = logging.getLogger(f'{__name__}.PDFColumn')

	def __init__(self, name, image, index, rect, hocr, tokens):
		self.name = name
		self.image = image
		self.index = index
		self.rect = rect
		self.hocr = hocr
		self.tokens = tokens


def tokenize_image(name, image, language='Eng', force=False):
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
				log.info(f'Generating hOCR for column {index} of {name}')

				tesseract.SetRectangle(*rect)

				hocr = tesseract.GetHOCRText(0)

				doc = html.fromstring(hocr)
				elements = doc.xpath("//*[@class='ocrx_word']")

				columns.append(PDFColumn(
					name,
					image,
					index,
					rect,
					hocr,
					[HOCRToken(e) for e in elements if e.text.strip() != '']
				))

	return columns


class HOCRTokenizer(Tokenizer):
	log = logging.getLogger(f'{__name__}.HOCRTokenizer')

	def tokenize(self, file, force=False):
		if file.suffix in {'.tiff', '.png'}:
			columns = tokenize_image(file, cv2.imread(str(file)), self.language.alpha_3)
		elif file.suffix == '.pdf':
			doc = fitz.open(str(file))
			columns = []
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
					columns.extend(tokenize_image(f'{file.stem}-page{pageno}', img, self.language.alpha_3))
		else:
			HOCRTokenizer.log.error(f'Cannot handle {file}')
			raise SystemExit(-1)

		all_tokens = [t for c in columns for t in c.tokens]

		HOCRTokenizer.log.debug(f'Found {len(all_tokens)} tokens, first 10: {all_tokens[:10]}')
	
		return self.generate_kbest(all_tokens)


Tokenizer.register(HOCRTokenizer, ['.pdf', '.tiff', '.png'])

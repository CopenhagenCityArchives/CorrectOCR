import locale
import logging
from contextlib import contextmanager
from functools import partial

import cv2
import numpy as np
import progressbar
from lxml import html

from ._super import Token, Tokenizer
from ..workspace import Workspace


@contextmanager
def c_locale():
	try:
		currlocale = locale.getlocale()
	except ValueError:
		currlocale = ('en_US', 'UTF-8')
	logging.getLogger(f'{__name__}.c_locale').debug(f'Current locale: {currlocale}')
	locale.setlocale(locale.LC_CTYPE, "C")
	yield
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


def columnize(filePath, columncount):
	log = logging.getLogger(f'{__name__}.columnize')

	if columncount != 2:
		log.error(f'Cannot columnize {columncount} columns, only 2')
		raise SystemExit(-1)

	image = cv2.imread(filePath)

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


def tokenize_image(filePath, language='Eng', force=False):
	log = logging.getLogger(f'{__name__}.tokenize_image')

	outfile = filePath.parent.joinpath(f'{filePath.stem}.json')
	if not force and outfile.is_file():
		log.info(f'Found hOCR for {filePath} at {outfile}')
		return Workspace.load(outfile)

	tokens = []

	with c_locale():
		# C locale workaround, see:
		# https://github.com/sirfz/tesserocr/issues/165
		# https://github.com/tesseract-ocr/tesseract/issues/1670
		# noinspection PyUnresolvedReferences
		from tesserocr import PyTessBaseAPI
		with PyTessBaseAPI(lang=language) as tesseract:
			tesseract.SetImageFile(str(filePath))

			for i, column in enumerate(columnize(str(filePath), 2)):
				log.info(f'Going to generate hOCR for column {i} of {filePath} at {outfile}')

				tesseract.SetRectangle(*column)

				hocr = tesseract.GetHOCRText(0)

				doc = html.fromstring(hocr)
				elements = doc.xpath("//*[@class='ocrx_word']")

				tokens.extend([HOCRToken(e) for e in elements if e.text.strip() != ''])
				#tokens.append({
				#	'image': str(filePath),
				#	'index': i,
				#	'rect': column,
				#	'hocr': hocr,
				#	'tokens': [HOCRToken(e) for e in elements]
				#})

	return tokens


def tokenize_directory(dirPath, language, extension='*.tiff', force=False):
	log = logging.getLogger(f'{__name__}.tokenize_directory')
	
	tokens = []
	
	log.info(f'Going to tokenize {extension} images in {dirPath}')
	for file in dirPath.glob(extension):
		tokens.extend(tokenize_image(file, language, force=force))
	
	return tokens


class HOCRTokenizer(Tokenizer):
	log = logging.getLogger(f'{__name__}.HOCRTokenizer')

	def tokenize(self, file, force=False):
		if file.suffix == '.tiff':
			tokens = tokenize_image(file, self.language.alpha_3)
		elif file.suffix == '.pdf':
			tokens = [] # TODO
			pass
		else:
			HOCRTokenizer.log.error(f'Cannot handle {file}')
			raise SystemExit(-1)

		HOCRTokenizer.log.debug(f'Found {len(tokens)} tokens, first 10: {tokens[:10]}')
	
		HOCRTokenizer.log.info(f'Generating {self.k}-best suggestions for each token')
		for i, token in enumerate(progressbar.progressbar(tokens)):
			if token in self.previousTokens:
				token._string = self.previousTokens[token].original # TODO HACK?
				token.update(other=self.previousTokens[token])
			else:
				token.update(kbest=self.hmm.kbest_for_word(token.original, self.k, self.dictionary))
			if not token.gold and token.original in self.wordAlignments:
				wa = self.wordAlignments.get(token.original, dict())
				closest = sorted(wa.items(), key=lambda x: x[0], reverse=True)
				#HOCRTokenizer.log.debug(f'{i} {token.original} {closest}')
				token.gold = closest[0][1]
			self.previousTokens[token.original] = token
			#HOCRTokenizer.log.debug(token.as_dict())

		HOCRTokenizer.log.debug(f'Generated for {len(tokens)} tokens, first 10: {tokens[:10]}')
		return tokens


Tokenizer.register(HOCRTokenizer, ['.pdf', '.tiff'])
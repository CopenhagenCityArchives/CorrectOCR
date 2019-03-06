import json
import logging

from lxml import html

from .tokenize import Token, TokenSegment
		

class COCRJSONCodec(json.JSONEncoder):
	log = logging.getLogger(f'{__name__}.COCRJSONEncoder')

	def default(self, obj):
		if isinstance(obj, TokenSegment):
			return {
				'COCRkind': 'TokenSegment',
				'fileid': obj.fileid,
				'page': obj.page,
				'column': obj.column,
				'rect': obj.rect,
				#'image': obj.image,
				'hocr': obj.hocr,
				'tokens': obj.tokens,
			}
		elif isinstance(obj, Token):
			return {
				'COCRkind': 'Token',
				'token': vars(obj),
			}
		elif isinstance(obj, html.HtmlElement):
			return {
				'COCRkind': 'html.HtmlElement',
				'element': html.tostring(obj),
			}
		else:
			#COCRJSONCodec.log.debug(f'Defaulting for {obj}')
			return super(COCRJSONCodec, self).default(obj)

	@staticmethod
	def object_hook(obj):
		log = logging.getLogger(f'{__name__}.COCRJSONobject_hook')
	
		if 'COCRkind' in obj:
			if obj['COCRkind'] == 'TokenSegment':
				return TokenSegment(
					obj['fileid'],
					obj['page'],
					obj['column'],
					obj['rect'],
					None,			# image
					obj['hocr'],
					obj['tokens'],
				)
			elif obj['COCRkind'] =='Token':
				return Token.from_dict(obj['token'])
			elif obj['COCRkind'] == 'html.HtmlElement':
				return html.fromstring(obj['element'])
		else:
			#log.debug(f'Defaulting for {obj}')
			return obj

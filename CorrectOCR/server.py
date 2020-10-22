import io
import logging
import random
from threading import Thread
from typing import Any

from flask import Flask, Response, g, json, redirect, request, url_for
from flask_cors import CORS
import requests

from . import progname
from .tokens._pdf import PDFToken
from .workspace import Workspace

def create_app(workspace: Workspace = None, config: Any = None):
	"""
	Creates and returns Flask app.

	:param workspace: TODO
	:param config: TODO
	"""
	log = logging.getLogger(f'{__name__}.server')

	# create and configure the app
	app = Flask(progname,
		instance_path = workspace.root if workspace else None,
	)
	CORS(app)

	app.config.from_mapping(
		host = config.host if config else None,
		threaded = True,
		#SECRET_KEY='dev', # TODO needed?
	)

	if config and config.debug:
		app.config.update(
			ENV = 'development',
			DEBUG = True,
		)
		logging.getLogger().setLevel(logging.DEBUG)

	@app.before_request
	def before_request():
		g.docs = {
			docid: {
				'tokens': workspace.docs[docid].tokens,
				'info_url': workspace.docs[docid].info_url,
			} for docid in workspace.docids_for_ext('.pdf', server_ready=True)
		} if workspace else {}
		g.discard_filter = lambda t: not t.is_discarded

	def is_authenticated(formdata) -> bool:
		#app.logger.debug(f'config.auth_endpoint: {config.auth_endpoint}')
		if not config.auth_endpoint or config.auth_endpoint == '':
			return True # no authentication...
		if config.auth_header not in formdata:
			return False
		r = requests.post(
			config.auth_endpoint,
			data={
				config.auth_header: formdata[config.auth_header]
			}
		)
		return r.status_code == 200

	@app.route('/health')
	def health():
		return 'OK', 200

	@app.route('/')
	def indexpage():
		"""
		Get an overview of the documents available for correction.
		
		.. :quickref: 1 Main; Get list of documents

		**Example response**:

		.. sourcecode:: http

		   HTTP/1.1 200 OK
		   Content-Type: application/json
		   
		   [
		     {
		       "docid": "<docid>",
		       "url": "/<docid>/tokens.json",
		       "info_url": "...",
		       "count": 100,
		       "corrected": 87
		     }
		   ]
		
		:>jsonarr string docid: ID for the document.
		:>jsonarr string url: URL to list of Tokens in doc.
		:>jsonarr string info_url: URL that provides more info about the document. See
		  workspace.docInfoBaseURL
		:>jsonarr int count: Total number of Tokens.
		:>jsonarr int corrected: Number of corrected Tokens.
		"""
		docindex = [{
			'docid': docid,
			'url': url_for('tokens', docid=docid),
			'info_url': doc['info_url'],
			'count': len(doc['tokens']),
			'corrected': doc['tokens'].corrected_count,
			'discarded': doc['tokens'].discarded_count
		} for docid, doc in g.docs.items()]
		return json.jsonify(docindex)

	@app.route('/<string:docid>/tokens.json')
	def tokens(docid):
		"""
		Get information about the :class:`Tokens<CorrectOCR.tokens.Token>` in a given document.
		
		.. :quickref: 2 Documents; Get list of tokens in document

		:param string docid: The ID of the requested document.

		**Example response**:

		.. sourcecode:: http

		   HTTP/1.1 200 OK
		   Content-Type: application/json
		   
		   [
		     {
		       "info_url": "/<docid>/token-0.json",
		       "image_url": "/<docid>/token-0.png",
		       "string": "Example",
		       "is_corrected": true
		     },
		     {
		       "info_url": "/<docid>/token-1.json",
		       "image_url": "/<docid>/token-1.png",
		       "string": "Exanpie",
		       "is_corrected": false
		     }
		   ]

		:>jsonarr string info_url: URL to Token info.
		:>jsonarr string image_url: URL to Token image.
		:>jsonarr string string: Current Token string.
		:>jsonarr bool is_corrected: Whether the Token has been corrected at the moment.
		"""
		if docid not in g.docs:
			return json.jsonify({
				'detail': f'Document "{docid}" not found.',
			}), 404
		tokenindex = [{
			'info_url': url_for('tokeninfo', docid=docid, index=n),
			'image_url': url_for('tokenimage', docid=docid, index=n),
			'string': (token.gold or token.original),
			'is_corrected': (token.gold is not None and token.gold.strip() != ''),
			'is_discarded': token.is_discarded,
		} for n, token in enumerate(filter(g.discard_filter, g.docs[docid]['tokens']))]
		return json.jsonify(tokenindex)

	@app.route('/<string:docid>/token-<int:index>.json')
	def tokeninfo(docid, index):
		"""
		Get information about a specific :class:`Token<CorrectOCR.tokens.Token>`
		
		**Note**: The data is not escaped; care must be taken when displaying in a browser.
		
		.. :quickref: 3 Tokens; Get token

		**Example response**:

		.. sourcecode:: http

		   HTTP/1.1 200 OK
		   Content-Type: application/json
		   
		   {
		     "1-best": "Jornben",
		     "1-best prob.": 2.96675056066388e-08,
		     "2-best": "Joreben",
		     "2-best prob.": 7.41372275428713e-10,
		     "3-best": "Jornhen",
		     "3-best prob.": 6.17986300962785e-10,
		     "4-best": "Joraben",
		     "4-best prob.": 5.52540106969346e-10,
		     "Bin": 2,
		     "Decision": "annotator",
		     "Doc ID": "7696",
		     "Gold": "",
		     "Heuristic": "a",
			 "Hyphenated": false,
			 "Discarded": false,
		     "Index": 2676,
		     "Original": "Jornben.",
		     "Selection": [],
		     "Token info": "...",
		     "Token type": "PDFToken",
		     "Page": 1,
		     "Frame": [0, 0, 100, 100],
		     "Annotation info": "...",
		     "image_url": "/7696/token-2676.png"
		   }
		
		:param string docid: The ID of the requested document.
		:param int index: The placement of the requested Token in the document.
		:return: A JSON dictionary of information about the requested :class:`Token<CorrectOCR.tokens.Token>`.
		    Relevant keys for frontend display include
		    `original` (uncorrected OCR result),
		    `gold` (corrected version, if available),
		    TODO
		"""
		if docid not in g.docs:
			return json.jsonify({
				'detail': f'Document "{docid}" not found.',
			}), 404
		if index >= len(g.docs[docid]['tokens']) or index < 0:
			return json.jsonify({
				'detail': f'Document "{docid}" does not have a token at {index}.',
			}), 404
		token = g.docs[docid]['tokens'][index]
		tokendict = vars(token)
		if 'image_url' not in tokendict:
			tokendict['image_url'] = url_for('tokenimage', docid=docid, index=index)
		return json.jsonify(tokendict)

	@app.route('/<string:docid>/token-<int:index>.json', methods=[ 'POST'])
	def update_token(docid, index):
		"""
		Update a given token with a `gold` transcription and/or hyphenation info.
		
		.. :quickref: 3 Tokens; Update token

		:param string docid: The ID of the requested document.
		:param int index: The placement of the requested Token in the document.
		
		:<json string gold: Set new correction for this Token.
		:<json string annotation info: Save some metadata about this correction (eg. username, date). Will only be saved if there is a gold correction.
		:<json string hyphenate: Optionally hyphenate to the `left` or `right`.
		
		:return: A JSON dictionary of information about the updated :class:`Token<CorrectOCR.tokens.Token>`.
		"""
		#app.logger.debug(f'request: {request} request.data: {request.data} request.json: {request.json}')
		if docid not in g.docs:
			return json.jsonify({
				'detail': f'Document "{docid}" not found.',
			}), 404
		if index >= len(g.docs[docid]['tokens']) or index < 0:
			return json.jsonify({
				'detail': f'Document "{docid}" does not have a token at {index}.',
			}), 404
		token = g.docs[docid]['tokens'][index]
		if 'gold' in request.json:
			if not is_authenticated(request.json):
				return json.jsonify({'error': 'Unauthorized.'}), 401
			token.gold = request.json['gold']
			app.logger.debug(f'Received new gold for token: {token}')
			if 'annotation_info' in request.json:
				app.logger.debug(f"Received annotation_info: {request.json['annotation_info']}")	
				token.annotation_info = request.json['annotation_info']
			g.docs[docid]['tokens'].save(token=token)
		if 'hyphenate' in request.json:
			app.logger.debug(f'Going to hyphenate: {request.json["hyphenate"]}')
			if request.json['hyphenate'] == 'left':
				t = g.docs[docid]['tokens'][index-1]
				t.is_hyphenated = True
				g.docs[docid]['tokens'].save(token=t)
			elif request.json['hyphenate'] == 'right':
				token.is_hyphenated = True
				g.docs[docid]['tokens'].save(token=token)
			else:
				return json.jsonify({
					'detail': f'Invalid hyphenation "{request.json["hyphenate"]}"',
				}), 400
		if 'discard' in request.json:
			app.logger.debug(f'Going to discard token.')
			token.is_discarded = True
			g.docs[docid]['tokens'].save(token=token)
		tokendict = vars(token)
		if 'image_url' not in tokendict:
			tokendict['image_url'] = url_for('tokenimage', docid=docid, index=index)
		return json.jsonify(tokendict)

	@app.route('/<string:docid>/token-<int:index>.png')
	def tokenimage(docid, index):
		"""
		Returns a snippet of the original document as an image, for comparing with the OCR result.
		
		.. :quickref: 3 Tokens; Get token image

		:param string docid: The ID of the requested document.
		:param int index: The placement of the requested Token in the document.
		:query int leftmargin: Optional left margin. See :meth:`PDFToken.extract_image()<CorrectOCR.tokens.PDFToken.extract_image>` for defaults. TODO
		:query int rightmargin: Optional right margin.
		:query int topmargin: Optional top margin.
		:query int bottommargin: Optional bottom margin.
		:return: A PNG image of the requested :class:`Token<CorrectOCR.tokens.Token>`.
		"""
		if docid not in g.docs:
			return json.jsonify({
				'detail': f'Document "{docid}" not found.',
			}), 404
		if index >= len(g.docs[docid]['tokens']) or index < 0:
			return json.jsonify({
				'detail': f'Document "{docid}" does not have a token at {index}.',
			}), 404
		token: PDFToken = g.docs[docid]['tokens'][index]
		if request.json:
			(docname, image) = token.extract_image(
				workspace,
				left=request.json.get('leftmargin'),
				right=request.json.get('rightmargin'),
				top=request.json.get('topmargin'),
				bottom=request.json.get('bottommargin')
			)
		else:
			(docname, image) = token.extract_image(workspace)

		with io.BytesIO() as output:
			image.save(output, format="PNG")
			return Response(output.getvalue(), mimetype='image/png')

	@app.route('/random')
	def rand():
		"""
		Returns a 302-redirect to a random token from a random document. TODO: filter by needing annotator
		
		.. :quickref: 3 Tokens; Get random token

		**Example response**:

		.. sourcecode:: http

		   HTTP/1.1 302 Found
		   Location: /<docid>/token-<index>.json
		"""
		docid = random.choice(list(g.docs.keys()))
		index = g.docs[docid]['tokens'].random_token_index(has_gold=False, is_discarded=False)
		return redirect(url_for('tokeninfo', docid=docid, index=index))

	# for local testing:
	@app.route('/auth', methods=['POST'])
	def auth():
		log.debug(f'request.json: {request.json}')
		authorized = request.json['auth_token'] == 'TEST'
		return json.jsonify({
			'authorized': authorized
		}), 200 if authorized else 401

	def add_and_prepare(uris):
		for uri in uris:
			log.info(f'Adding {uri}')
			doc_id = workspace.add_doc(uri)
			log.info(f'Preparing {doc_id}')
			workspace.docs[doc_id].prepare('server', k=config.k)

	@app.route('/add_docs', methods=['POST'])
	def add_docs():
		"""
		Adds a number of documents to the backend.
		
		Each URL will be downloaded and tokens will prepared in a background thread. Once they are prepared, they will become available in the other endpoints.
		
		.. :quickref: 2 Documents; Add more documents

		:<json list urls: A list of URLS to documents.
		"""
		#log.debug(f'request.data: {request.data}')
		#log.debug(f'request.json: {request.json}')
		#log.debug(f'request.form: {request.form}')
		if request.json and 'urls' in request.json:
			thread = Thread(target=add_and_prepare, args=(request.json['urls'], ))
			thread.start()
			return json.jsonify({
				'detail': f'Adding and preparing documents from list of URLs. They will become available once prepared.',
			}), 200
		else:
			return json.jsonify({
				'detail': f'No document URLs specified.',
			}), 400

	@app.route('/test')
	def test():
		log.debug(f'hit test endpoint')
		return 'test', 200

	return app

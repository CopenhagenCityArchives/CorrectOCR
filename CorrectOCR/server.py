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

	if config.profile:
		log.info('Using Werkzeug application profiler')
		from werkzeug.middleware.profiler import ProfilerMiddleware
		app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[10], profile_dir=workspace.root)

	@app.before_request
	def before_request():
		g.docs = {
			docid: {
				'tokens': workspace.docs[docid].tokens,
				'info_url': workspace.docs[docid].info_url,
			} for docid in workspace.docids_for_ext('.pdf', server_ready=True)
		} if workspace else {}
		g.discard_filter = lambda t: not t.is_discarded

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
		       "corrected": 87,
		       "corrected_by_model": 80,
		       "discarded": 10,
		       "last_modified": 1605255523
		     }
		   ]
		
		:>jsonarr string docid: ID for the document.
		:>jsonarr string url: URL to list of Tokens in doc.
		:>jsonarr string info_url: URL that provides more info about the document. See
		  workspace.docInfoBaseURL
		:>jsonarr int count: Total number of Tokens.
		:>jsonarr int corrected: Number of corrected Tokens.
		:>jsonarr int corrected_by_model: Number of Tokens that were automatically corrected by the model.
		:>jsonarr int discarded: Number of discarded Tokens.
		:>jsonarr int last_modified: The date/time of the last modified token.
		"""
		docindex = [{
			'docid': docid,
			'url': url_for('tokens', docid=docid),
			'info_url': doc['info_url'],
			'count': len(doc['tokens']),
			'corrected': doc['tokens'].corrected_count,
			'corrected_by_model': doc['tokens'].corrected_by_model_count,
			'discarded': doc['tokens'].discarded_count,
			'last_modified': doc['tokens'].last_modified.timestamp() if doc['tokens'].last_modified else None,
		} for docid, doc in g.docs.items()]
		return json.jsonify(docindex)

	@app.route('/<string:docid>/tokens.json')
	def tokens(docid):
		"""
		Get information about the :class:`Tokens<CorrectOCR.tokens.Token>` in a given document.
		
		Returns ``404`` if the document cannot be found, otherwise ``200``.
		
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
		       "is_corrected": true,
		       "is_discarded": false,
		       "requires_annotator": false,
		       "last_modified": 1605255523
		     },
		     {
		       "info_url": "/<docid>/token-1.json",
		       "image_url": "/<docid>/token-1.png",
		       "string": "Exanpie",
		       "is_corrected": false,
		       "is_discarded": false,
		       "requires_annotator": true,
		       "last_modified": null
		     }
		   ]

		:>jsonarr string info_url: URL to Token info.
		:>jsonarr string image_url: URL to Token image.
		:>jsonarr string string: Current Token string.
		:>jsonarr bool is_corrected: Whether the Token has been corrected at the moment.
		:>jsonarr bool is_discarded: Whether the Token has been discarded at the moment.
		:>jsonarr bool last_modified: The date/time when the token was last modified.
		"""
		if docid not in g.docs:
			return json.jsonify({
				'detail': f'Document "{docid}" not found.',
			}), 404
		tokenindex = [{
			'info_url': url_for('tokeninfo', docid=docid, index=n),
			'image_url': url_for('tokenimage', docid=docid, index=n),
			'string': tv['string'],
			'is_corrected': tv['is_corrected'],
			'is_discarded': tv['is_discarded'],
			'requires_annotator': tv['requires_annotator'],
			'last_modified': tv['last_modified'].timestamp() if tv['last_modified'] else None,
		} for n, tv in enumerate(g.docs[docid]['tokens'].overview)]
		return json.jsonify(tokenindex)

	@app.route('/<string:docid>/token-<int:index>.json')
	def tokeninfo(docid, index):
		"""
		Get information about a specific :class:`Token<CorrectOCR.tokens.Token>`.
		
		Returns ``404`` if the document or token cannot be found, otherwise ``200``.
		
		**Note**: If the token is the second part of a hyphenated token, a ``302``-redirect to the previous token will be returned.

		**Note**: The data is not escaped; care must be taken when displaying in a browser.
		
		.. :quickref: 3 Tokens; Get token

		**Example response**:

		.. sourcecode:: http

		   HTTP/1.1 200 OK
		   Content-Type: application/json
		   
		   {
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
		     "k-best": {
			   1: { "candidate": "Jornben", "probability": 2.96675056066388e-08 },
			   2: { "candidate": "Joreben", "probability": 7.41372275428713e-10 },
			   3: { "candidate": "Jornhen", "probability": 6.17986300962785e-10 },
			   4: { "candidate": "Joraben", "probability": 5.52540106969346e-10 }
		     },
		     "Last Modified": 1605255523
		   }
		
		:param string docid: The ID of the requested document.
		:param int index: The placement of the requested Token in the document.
		:return: A JSON dictionary of information about the requested :class:`Token<CorrectOCR.tokens.Token>`.
		    Relevant keys for frontend display include
		    `original` (uncorrected OCR result),
		    `gold` (corrected version, if available). For further information, see the Token class.
		"""
		if docid not in g.docs:
			return json.jsonify({
				'detail': f'Document "{docid}" not found.',
			}), 404
		if index >= len(g.docs[docid]['tokens']) or index < 0:
			return json.jsonify({
				'detail': f'Document "{docid}" does not have a token at {index}.',
			}), 404
		prev_token = g.docs[docid]['tokens'][index-1]
		if prev_token.is_hyphenated:
			return redirect(url_for('tokeninfo', docid=prev_token.docid, index=prev_token.index))
		token = g.docs[docid]['tokens'][index]
		tokendict = vars(token)
		if 'image_url' not in tokendict:
			tokendict['image_url'] = url_for('tokenimage', docid=docid, index=index)
		return json.jsonify(tokendict)

	@app.route('/<string:docid>/token-<int:index>.json', methods=[ 'POST'])
	def update_token(docid, index):
		"""
		Update a given token with a `gold` transcription and/or hyphenation info.
		
		Returns ``404`` if the document or token cannot be found, otherwise ``200``.
		
		If an invalid ``hyphenate`` value is submitted, status code ``400`` will be returned.
		
		**Note**: If ``gold`` and ``hyphenate`` are supplied, the ``gold`` value will be
		inspected. If it contains a hyphen, the left and right parts will be set on the
		respective tokens. If it does not, the gold will be set on the leftmost token,
		and the right one discarded.
		
		**Note**: If the hyphenation is set to ``left``, a redirect to the new "head" token will be returned.
		
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
		if 'hyphenate' in request.json:
			app.logger.debug(f'Going to hyphenate: {request.json["hyphenate"]}')
			if request.json['hyphenate'] == 'left':
				token.gold = ''
				prev_token = g.docs[docid]['tokens'][index-1]
				gold = request.json.get('gold', None)
				if gold:
					if '-' in gold:
						a, b = gold.split('-')
						prev_token.gold = a + '-'
						token.gold = b
					else:
						prev_token.gold = gold
						token.is_discarded = True
				prev_token.is_hyphenated = True
				prev_token.drop_cached_image()
				g.docs[docid]['tokens'].save(token=prev_token)
				return redirect(url_for('tokeninfo', docid=prev_token.docid, index=prev_token.index))
			elif request.json['hyphenate'] == 'right':
				next_token = g.docs[docid]['tokens'][index+1]
				gold = request.json.get('gold', None)
				if gold:
					if '-' in gold:
						a, b = gold.split('-')
						token.gold = a + '-'
						next_token.gold = b
					else:
						token.gold = gold
						next_token.is_discarded = True
				token.is_hyphenated = True
				token.drop_cached_image()
				next_token.gold = ''
				next_token.drop_cached_image()
				g.docs[docid]['tokens'].save(token=next_token)
			else:
				return json.jsonify({
					'detail': f'Invalid hyphenation "{request.json["hyphenate"]}"',
				}), 400
		elif 'gold' in request.json:
			token.gold = request.json['gold']
			app.logger.debug(f'Received new gold for token: {token}')
			if 'annotation_info' in request.json:
				app.logger.debug(f"Received annotation_info: {request.json['annotation_info']}")	
				token.annotation_info = request.json['annotation_info']
		elif 'discard' in request.json:
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
		
		Returns ``404`` if the document or token cannot be found, otherwise ``200``.
		
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

	def add_and_prepare(uris, autocrop, precache_images, force_prepare):
		for uri in uris:
			log.info(f'Adding {uri}')
			doc_id = workspace.add_doc(uri)
			log.info(f'Preparing {doc_id}')
			workspace.docs[doc_id].prepare('server', k=config.k, dehyphenate=config.dehyphenate, force=force_prepare)
			if autocrop:
				workspace.docs[doc_id].crop_tokens()
			if precache_images:
				workspace.docs[doc_id].precache_images()
			log.info(f'Document {doc_id} is ready.')

	@app.route('/add_docs', methods=['POST'])
	def add_docs():
		"""
		Adds a number of documents to the backend.
		
		Each URL will be downloaded and tokens will prepared in a background thread. Once they are prepared, they will become available in the other endpoints.
		
		Returns ``400`` if no URLs are specified, otherwise ``200``.
		
		.. :quickref: 2 Documents; Add more documents

		:<json list urls: A list of URLS to documents.
		"""
		#log.debug(f'request.data: {request.data}')
		#log.debug(f'request.json: {request.json}')
		#log.debug(f'request.form: {request.form}')
		if request.json and 'urls' in request.json:
			thread = Thread(target=add_and_prepare, args=(request.json['urls'], request.json.get('autocrop', True), request.json.get('precache_images', True), request.json.get('force_prepare', True)))
			thread.start()
			return json.jsonify({
				'detail': f'Adding and preparing documents from list of URLs. They will become available once prepared.',
			}), 200
		else:
			return json.jsonify({
				'detail': f'No document URLs specified.',
			}), 400

	return app

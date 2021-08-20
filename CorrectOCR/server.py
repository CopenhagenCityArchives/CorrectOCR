import io
import logging
import os
import random
import traceback
from pprint import pformat
from threading import Thread
from typing import Any

from flask import Flask, Response, g, json, redirect, request, send_file, url_for
from flask_cors import CORS
import requests

from . import progname
from .fileio import FileIO
from .tokens._pdf import PDFToken
from .workspace import Workspace

def create_app(workspace: Workspace = None, config: Any = None):
	"""
	Creates and returns Flask app.

	:param workspace: TODO
	:param config: TODO
	"""
	if workspace is None:
		from .__main__ import setup
		workspace, config = setup(['server'])
	log = logging.getLogger(f'{__name__}.server')
	log.info(f'Server configuration:\n{pformat(vars(config))}')

	static_folder = str(FileIO.imageCache().resolve())
	log.info(f'static_folder: {static_folder}')
	static_url_path = '/images' # TODO config
	log.info(f'static_url_path: {static_url_path}')

	# create and configure the app
	app = Flask(progname,
		instance_path = workspace.root if workspace else None,
		static_url_path = static_url_path,
		static_folder = static_folder,
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
		app.wsgi_app = ProfilerMiddleware(app.wsgi_app, restrictions=[10])

	pid = os.getpid()

	@app.before_request
	def before_request():
		app.logger.debug(f'BEGIN process {pid} handling request: {request.environ}')
		g.docs = workspace.documents(server_ready=True)
		#app.logger.debug(f'g.docs: {g.docs}')
		g.discard_filter = lambda t: not t.is_discarded
		if g.doc_id is not None:
			if g.doc_id not in g.docs:
				return json.jsonify({
					'detail': f'Document "{g.doc_id}" not found.',
				}), 404
			if g.doc_index is not None:
				if g.doc_index >= len(g.docs[g.doc_id].tokens):
					return json.jsonify({
						'detail': f'Document "{g.doc_id}" does not have a token at {g.doc_index}.',
					}), 404
				g.token = g.docs[g.doc_id].tokens[g.doc_index]

	@app.after_request
	def after_request(response):
		app.logger.debug(f'END process {pid} handling request: {request.environ}')
		return response

	@app.url_value_preprocessor
	def get_token(endpoint, values):
		if values is None:
			values = {}
		g.doc_id = values.pop('doc_id', None)
		g.doc_index = values.pop('doc_index', None)
		app.logger.debug(f'Using doc_id {g.doc_id} and doc_index {g.doc_index}')

	@app.route('/health')
	def health():
		return 'OK', 200

	# for sorting docindex to bring unfinished docs to the top
	sort_key = lambda d: (d['stats']['done'], d['docid'])

	def image_url(should_generate=False):
		if should_generate:
			app.logger.debug(f'Checking if image exists for: {g.token}')
			if not g.token.cached_image_path.exists():
				app.logger.debug(f'Generating image for: {g.token}')
				try:
					_ = g.token.extract_image(workspace)
				except PermissionError as e:
					app.logger.error(f'Could not generate image for {g.token}: {e}')
		return f'{app.static_url_path}/{g.doc_id}/{g.doc_index}.png'

	@app.route('/')
	def indexpage():
		"""
		Get an overview of the documents available for correction.
		
		The list will not include documents that the backend considers 'done',
		but they can still be accesses via the other endpoints.
		
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
		docindex = []
		for docid, doc in g.docs.items():
			stats = doc.tokens.stats
			if len(doc.tokens) > 0:
				if stats['done']:
					#app.logger.debug(f'Skipping document marked done: {docid}')
					continue
				if stats['token_count'] == stats['corrected_count'] + stats['error_count'] + stats['discarded_count']:
					app.logger.debug(f'Skipping document without correctable tokens: {docid}')
					continue
				docindex.append({
					'docid': docid,
					'url': url_for('tokens', doc_id=docid),
					'info_url': doc.info_url,
					'count': stats['token_count'],
					'corrected': stats['corrected_count'],
					'corrected_by_model': stats['corrected_by_model_count'],
					'discarded': stats['discarded_count'],
					'stats': stats,
					'last_modified': doc.tokens.last_modified.timestamp() if doc.tokens.last_modified else None,
				})
		return json.jsonify(sorted(docindex, key=sort_key))

	@app.route('/<string:doc_id>/tokens.json')
	def tokens():
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
		       "has_error": false,
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
		tokenindex = [{
			'info_url': url_for('tokeninfo', doc_id=g.doc_id, doc_index=n),
			'image_url': image_url(),
			'string': tv['string'],
			'is_corrected': tv['is_corrected'],
			'is_discarded': tv['is_discarded'],
			'requires_annotator': tv['requires_annotator'],
			'has_error': tv['has_error'],
			'last_modified': tv['last_modified'].timestamp() if tv['last_modified'] else None,
		} for n, tv in enumerate(g.docs[g.doc_id].tokens.overview)]
		return json.jsonify(tokenindex)

	@app.route('/<string:doc_id>/token-<int:doc_index>.json')
	def tokeninfo():
		"""
		Get information about a specific :class:`Token<CorrectOCR.tokens.Token>`.
		
		Returns ``404`` if the document or token cannot be found, otherwise ``200``.
		
		**Note**: If the token is the second part of a hyphenated token, and the server is configured for it, a ``302``-redirect to the previous token will be returned.

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
		
		:param string doc_id: The ID of the requested document.
		:param int doc_index: The placement of the requested Token in the document.
		:return: A JSON dictionary of information about the requested :class:`Token<CorrectOCR.tokens.Token>`.
		    Relevant keys for frontend display include
		    `original` (uncorrected OCR result),
		    `gold` (corrected version, if available). For further information, see the Token class.
		"""
		if config.redirect_hyphenated and g.doc_index > 0:
			prev_token = g.docs[g.doc_id].tokens[g.doc_index-1]
			if prev_token.is_hyphenated:
				return redirect(url_for('tokeninfo', doc_id=prev_token.docid, doc_index=prev_token.index))
		tokendict = vars(g.token)
		if tokendict['Original'][-1] == '\xad': # soft hyphen
			tokendict['Original'] = tokendict['Original'][:-1] + '-'
		if tokendict['Gold'] and tokendict['Gold'][-1] == '\xad': # soft hyphen
			tokendict['Gold'] = tokendict['Gold'][:-1] + '-'
		if g.token.is_hyphenated:
			# TODO ugly hack so users see he joined token....
			next_token = g.docs[g.doc_id].tokens[g.doc_index+1]
			tokendict['Original'] += next_token.original
		if 'image_url' not in tokendict:
			tokendict['image_url'] = image_url(should_generate=config.dynamic_images)
		return json.jsonify(tokendict)

	def hyphenate_token(tokens, index, hyphenation, gold):
		"""
			Will return the other side of the hyphenation (prev/next) token, if any.
			
			It is the responsibility of the caller to save the token.
		"""
		token = tokens[index]
		if hyphenation == 'left':
			if index == 0:
				raise IndexError(f'Cannot hyphenate first token to the left')
			prev_token = tokens[index-1]
			#app.logger.debug(f'prev_token before: {prev_token}')
			if gold:
				if '-' in gold:
					a, b = gold.split('-')
					prev_token.gold = a + '\xad' # soft hyphen
					token.gold = b
				else:
					prev_token.gold = gold
					token.gold = ''
					token.is_discarded = True
			prev_token.is_hyphenated = True
			if config.dynamic_images:
				prev_token.drop_cached_image()
				token.drop_cached_image()
			#app.logger.debug(f'prev_token after: {prev_token}')
			return prev_token
		elif hyphenation == 'right':
			if index == len(tokens)-1:
				raise IndexError(f'Cannot hyphenate last token to the right')
			next_token = tokens[index+1]
			#app.logger.debug(f'next_token before: {next_token}')
			if gold:
				if '-' in gold:
					a, b = gold.split('-')
					token.gold = a + '\xad' # soft hyphen
					next_token.gold = b
				else:
					token.gold = gold
					next_token.gold = ''
					next_token.is_discarded = True
			token.is_hyphenated = True
			if config.dynamic_images:
				token.drop_cached_image()
				next_token.drop_cached_image()
			#app.logger.debug(f'next_token after: {next_token}')
			return next_token
		elif hyphenation == 'split':
			if token.is_hyphenated:
				token.is_hyphenated = False
			else:
				prev_token = tokens[index-1]
				if prev_token.is_hyphenated:
					token.is_hyphenated = False
				else:
					raise ValueError(f'Cannot dehyphenate standalone token.')
		else:
			raise ValueError(f'Invalid hyphenation direction: "{direction}"')

	@app.route('/<string:doc_id>/token-<int:doc_index>.json', methods=[ 'POST'])
	def update_token():
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
		
		:return: A JSON dictionary of information about the updated :class:`Token<CorrectOCR.tokens.Token>`. *NB*: If the hyphenation is set to ``left``, a redirect to the new "head" token will be returned.
		"""
		#app.logger.debug(f'request: {request} request.data: {request.data} request.json: {request.json}')
		if 'error' in request.json:
			app.logger.debug(f'Received error for token: {g.token}')
			g.token.has_error = True
		elif 'hyphenate' in request.json:
			app.logger.debug(f'Going to hyphenate: {request.json["hyphenate"]}')
			try:
				t = hyphenate_token(g.docs[g.doc_id].tokens, g.doc_index, request.json['hyphenate'], request.json.get('gold', None))
				g.docs[g.doc_id].tokens.save(token=t)
			except Exception as e:
				app.logger.error(traceback.format_exc())
				return json.jsonify({
					'detail': str(e),
				}), 400
		elif 'gold' in request.json:
			app.logger.debug(f'Received new gold for token: {g.token}')
			if g.token.is_hyphenated:
				app.logger.debug(f'The token is already hyphenated, will set parts as required.')
				try:
					t = hyphenate_token(g.docs[g.doc_id].tokens, g.doc_index, 'right', request.json['gold'])
					g.docs[g.doc_id].tokens.save(token=t)
				except Exception as e:
					app.logger.error(traceback.format_exc())
					return json.jsonify({
						'detail': str(e),
					}), 400
			else:
				g.token.gold = request.json['gold']
		elif 'discard' in request.json:
			app.logger.debug(f'Going to discard token.')
			g.token.is_discarded = True
		g.token.annotations.append(request.json)
		g.docs[g.doc_id].tokens.save(token=g.token)
		return tokeninfo()

	@app.route('/<string:doc_id>/token-<int:doc_index>.png')
	def tokenimage():
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
		if config.dynamic_images and request.json:
			(docname, image) = g.token.extract_image(
				workspace,
				left=request.json.get('leftmargin'),
				right=request.json.get('rightmargin'),
				top=request.json.get('topmargin'),
				bottom=request.json.get('bottommargin')
			)
			with io.BytesIO() as output:
				image.save(output, format="PNG")
				return Response(output.getvalue(), mimetype='image/png')
		elif g.token.cached_image_path.exists():
			return send_file(g.token.cached_image_path)
		elif config.dynamic_images:
			(docname, image) = token.extract_image(workspace)
			with io.BytesIO() as output:
				image.save(output, format="PNG")
				return Response(output.getvalue(), mimetype='image/png')
		else:
			return json.jsonify({
				'detail': f'Token {index} in document "{doc_id}" does not have a an image.',
			}), 404

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
		index = g.docs[docid].tokens.random_token_index(has_gold=False, is_discarded=False)
		return redirect(url_for('tokeninfo', doc_id=docid, doc_index=index))

	@app.route('/doc_stats')
	def stats():
		docindex = []
		for docid, doc in workspace.documents():
			stats = doc.tokens.stats
			if len(doc.tokens) > 0:
				docindex.append({
					'docid': docid,
					'url': url_for('tokens', docid=docid),
					'info_url': doc.info_url,
					'server_ready': doc.tokens.server_ready,
					'count': len(doc.tokens),
					'stats': stats,
					'last_modified': doc.tokens.last_modified.timestamp() if doc.tokens.last_modified else None,
				})
		return json.jsonify(docindex)

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

	#@app.route('/add_docs', methods=['POST'])
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
			thread = Thread(
				target=add_and_prepare,
				args=(
					request.json['urls'],
					request.json.get('autocrop', True),
					request.json.get('precache_images', True),
					request.json.get('force_prepare', True)
				)
			)
			thread.daemon = True
			thread.start()
			return json.jsonify({
				'detail': f'Adding and preparing documents from list of URLs. They will become available once prepared.',
			}), 200
		else:
			return json.jsonify({
				'detail': f'No document URLs specified.',
			}), 400

	return app

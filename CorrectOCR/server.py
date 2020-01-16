import io
import logging
import random
from typing import Any

from flask import Flask, Response, g, json, redirect, request, url_for
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
	app.config.from_mapping(
		host = config.host if config else None,
		threaded=True,
		#SECRET_KEY='dev', # TODO needed?
	)

	@app.before_request
	def before_request():
		g.docs = {
			docid: {
				'tokens': workspace.autocorrectedTokens(docid, k=config.k),
			} for docid in workspace.paths if workspace.paths[docid].ext == '.pdf'
		} if workspace else {}

	def is_authenticated(formdata) -> bool:
		if config.auth_header not in formdata:
			return False
		r = requests.post(
			config.auth_endpoint,
			data={
				config.auth_header: formdata[config.auth_header]
			}
		)
		return r.status_code == 200

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
		       "count": 100,
		       "corrected": 87
		     }
		   ]
		
		:>jsonarr string docid: ID for the document.
		:>jsonarr string url: URL to list of Tokens in doc.
		:>jsonarr int count: Total number of Tokens.
		:>jsonarr int corrected: Number of corrected Tokens.
		"""
		docindex = [{
			'docid': docid,
			'url': url_for('tokens', docid=docid),
			'count': len(doc['tokens']),
			'corrected': len([t for t in doc['tokens'] if t.gold]),
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
		} for n, token in enumerate(g.docs[docid]['tokens'])]
		return json.jsonify(tokenindex)

	@app.route('/<string:docid>/token-<int:index>.json')
	def tokeninfo(docid, index):
		"""
		Get information about a specific :class:`Token<CorrectOCR.tokens.Token>`
		
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
		     "File ID": "7696",
		     "Gold": "",
		     "Heuristic": "a",
		     "Index": 2676,
		     "Original": "Jornben.",
		     "Selection": [],
		     "Token info": "...",
		     "Token type": "PDFToken",
		     "image_url": "/7696/token-2676.png"
		   }
		
		:param string docid: The ID of the requested document.
		:param int index: The placement of the requested Token in the document.
		:return: A JSON dictionary of information about the requested :class:`Token<CorrectOCR.tokens.Token>`.
		    Relevant keys for frontend display are
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
		
		:form gold: Set new correction for this Token.
		:form hyphenate: Optionally hyphenate to the `left` or `right`.

		:param string docid: The ID of the requested document.
		:param int index: The placement of the requested Token in the document.
		:return: A JSON dictionary of information about the updated :class:`Token<CorrectOCR.tokens.Token>`.
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
		if 'gold' in request.form:
			if not is_authenticated(request.form):
				return json.jsonify({'error': 'Unauthorized.'}), 401
			token.gold = request.form['gold']
			app.logger.debug(f'Received new gold for token: {token}')
			g.docs[docid]['tokens'].save(token=token)
		if 'hyphenate' in request.form:
			pass # TODO
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
		(docname, image) = token.extract_image(
			workspace,
			left=request.form.get('leftmargin'),
			right=request.form.get('rightmargin'),
			top=request.form.get('topmargin'),
			bottom=request.form.get('bottommargin')
		)
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
		g.docs = get_g.docs()
		docid = random.choice(list(g.docs.keys()))
		index = random.randint(0, len(g.docs[docid]['tokens']))
		return redirect(url_for('tokeninfo', docid=docid, index=index))

	# for local testing:
	@app.route('/auth', methods=['POST'])
	def auth():
		log.debug(f'request.form: {request.form}')
		authorized = request.form['auth_token'] == 'TEST'
		return json.jsonify({
			'authorized': authorized
		}), 200 if authorized else 401

	return app

import io
import logging
import random

from flask import Flask, Response, json, redirect, request, url_for
import requests

from . import progname
from .tokens._pdf import PDFToken
from .workspace import Workspace


def create_app(workspace: Workspace = None, config = None):
	log = logging.getLogger(f'{__name__}.server')

	# create and configure the app
	app = Flask(progname,
		instance_path = workspace.root if workspace else None,
	)
	app.config.from_mapping(
		host = config.host,
		threaded=True,
		#SECRET_KEY='dev', # TODO needed?
	)

	def get_docs():
		return {
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
		Get an overview of the docs available for correction.

		:>jsonarr string url: URL to list of Tokens in doc.
		:>jsonarr int count: Total number of Tokens.
		:>jsonarr int corrected: Number of corrected Tokens.
		"""
		docs = get_docs()
		docindex = [{
			'url': url_for('tokens', docid=docid),
			'count': len(doc['tokens']),
			'corrected': len([t for t in doc['tokens'] if t.gold]),
		} for docid, doc in docs.items()]
		return json.jsonify(docindex)

	@app.route('/<docid>/tokens.json')
	def tokens(docid):
		"""
		Get information about the :class:`Tokens<CorrectOCR.tokens.Token>` in a given doc.

		:param docid: The ID of the doc containing the tokens. TODO

		:>jsonarr string info_url: URL to Token info.
		:>jsonarr string image_url: URL to Token image.
		:>jsonarr string string: Current Token string.
		:>jsonarr bool is_corrected: Whether the Token has been corrected at the moment.
		"""
		docs = get_docs()
		tokenindex = [{
			'info_url': url_for('tokeninfo', docid=docid, index=n),
			'image_url': url_for('tokenimage', docid=docid, index=n),
			'string': (token.gold or token.original),
			'is_corrected': (token.gold is not None and token.gold.strip() != ''),
		} for n, token in enumerate(docs[docid]['tokens'])]
		return json.jsonify(tokenindex)

	@app.route('/<docid>/token-<int:index>.json', methods=['GET', 'POST'])
	def tokeninfo(docid, index):
		"""
		:form gold: Set new correction for this Token (optional).

		:param string docid: The ID of the doc containing the Tokens.
		:param int index: The index of the Token in the doc.
		:return: A JSON dictionary of the requested :class:`Token<CorrectOCR.tokens.Token>`.
		"""
		docs = get_docs()
		token = docs[docid]['tokens'][index]
		if request.method == 'POST' and 'gold' in request.form:
			if not is_authenticated(request.form):
				return json.jsonify({'error': 'Unauthorized.'}), 401
			token.gold = request.form['gold']
			app.logger.debug(f'Received new gold for token: {token}')
			docs[docid]['tokens'].save(token=token)
		tokendict = vars(token)
		if 'image_url' not in tokendict:
			tokendict['image_url'] = url_for('tokenimage', docid=docid, index=index)
		return json.jsonify(tokendict)

	@app.route('/<docid>/token-<int:index>.png')
	def tokenimage(docid, index):
		"""
		:param string docid: The ID of the doc containing the Tokens.
		:param int index: The index of the Token in the doc.
		:return: A PNG image of the requested :class:`Token<CorrectOCR.tokens.Token>`.
		"""
		docs = get_docs()
		token: PDFToken = docs[docid]['tokens'][index]
		(docname, image) = token.extract_image(workspace)
		with io.BytesIO() as output:
			image.save(output, format="PNG")
			return Response(output.getvalue(), mimetype='image/png')

	@app.route('/random')
	def rand():
		docs = get_docs()
		docid = random.choice(list(docs.keys()))
		index = random.randint(0, len(docs[docid]['tokens']))
		return redirect(url_for('tokeninfo', docid=docid, index=index))

	# for local testing:
	@app.route('/auth', methods=['POST'])
	def auth():
		log.debug(f'request.form: {request.form}')
		authorized = request.form['auth_token'] == 'TEST'
		return json.jsonify({'Authorized': authorized}), 200 if authorized else 401

	return app

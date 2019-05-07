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

	def get_files():
		return {
			fileid: {
				'tokens': workspace.autocorrectedTokens(fileid, k=config.k),
			} for fileid in workspace.paths if workspace.paths[fileid].ext == '.pdf'
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
	def index():
		"""
		Get an overview of the files available for correction.

		:>jsonarr string url: URL to list of Tokens in file.
		:>jsonarr int count: Total number of Tokens.
		:>jsonarr int corrected: Number of corrected Tokens.
		"""
		files = get_files()
		fileindex = [{
			'url': url_for('tokens', fileid=fileid),
			'count': len(file['tokens']),
			'corrected': len([t for t in file['tokens'] if t.gold]),
		} for fileid, file in files.items()]
		return json.jsonify(fileindex)

	@app.route('/<fileid>/tokens.json')
	def tokens(fileid):
		"""
		Get information about the :class:`Tokens<CorrectOCR.tokens.Token>` in a given file.

		:param fileid: The ID of the file containing the tokens. TODO

		:>jsonarr string info_url: URL to Token info.
		:>jsonarr string image_url: URL to Token image.
		:>jsonarr string string: Current Token string.
		:>jsonarr bool is_corrected: Whether the Token has been corrected at the moment.
		"""
		files = get_files()
		tokenindex = [{
			'info_url': url_for('tokeninfo', fileid=fileid, index=n),
			'image_url': url_for('tokenimage', fileid=fileid, index=n),
			'string': (token.gold or token.original),
			'is_corrected': (token.gold is not None and token.gold.strip() != ''),
		} for n, token in enumerate(files[fileid]['tokens'])]
		return json.jsonify(tokenindex)

	@app.route('/<fileid>/token-<int:index>.json', methods=['GET', 'POST'])
	def tokeninfo(fileid, index):
		"""
		:form gold: Set new correction for this Token (optional).

		:param string fileid: The ID of the file containing the Tokens.
		:param int index: The index of the Token in the file.
		:return: A JSON dictionary of the requested :class:`Token<CorrectOCR.tokens.Token>`.
		"""
		files = get_files()
		token = files[fileid]['tokens'][index]
		if request.method == 'POST' and 'gold' in request.form:
			if not is_authenticated(request.form):
				return json.jsonify({'error': 'Unauthorized.'}), 401
			token.gold = request.form['gold']
			app.logger.debug(f'Received new gold for token: {token}')
			files[fileid]['tokens'].save(token=token)
		tokendict = vars(token)
		if 'image_url' not in tokendict:
			tokendict['image_url'] = url_for('tokenimage', fileid=fileid, index=index)
		return json.jsonify(tokendict)

	@app.route('/<fileid>/token-<int:index>.png')
	def tokenimage(fileid, index):
		"""
		:param string fileid: The ID of the file containing the Tokens.
		:param int index: The index of the Token in the file.
		:return: A PNG image of the requested :class:`Token<CorrectOCR.tokens.Token>`.
		"""
		files = get_files()
		token: PDFToken = files[fileid]['tokens'][index]
		(filename, image) = token.extract_image(workspace)
		with io.BytesIO() as output:
			image.save(output, format="PNG")
			return Response(output.getvalue(), mimetype='image/png')

	@app.route('/random')
	def rand():
		files = get_files()
		fileid = random.choice(list(files.keys()))
		index = random.randint(0, len(files[fileid]['tokens']))
		return redirect(url_for('tokeninfo', fileid=fileid, index=index))

	# for local testing:
	@app.route('/auth', methods=['POST'])
	def auth():
		log.debug(f'request.form: {request.form}')
		authorized = request.form['auth_token'] == 'TEST'
		return json.jsonify({'Authorized': authorized}), 200 if authorized else 401

	return app

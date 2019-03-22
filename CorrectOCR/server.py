import io

from flask import Flask, Response, json, request, url_for

from . import progname
from .fileio import FileIO
from .tokens._pdf import PDFToken
from .workspace import Workspace


def create_app(workspace: Workspace, config):
	# create and configure the app
	app = Flask(progname,
		instance_path=workspace.root,
	)
	app.config.from_mapping(
		#SECRET_KEY='dev', # TODO needed?
	)

	files = {
		fileid: {
			'tokens': workspace.autocorrectedTokens(fileid, k=config.k),
		} for fileid in workspace.paths if workspace.paths[fileid].ext == '.pdf'
	}

	@app.route('/')
	def index():
		fileindex = [{
			'url': url_for('tokens', fileid=fileid),
			'count': len(file['tokens']),
			'corrected': len([t for t in file['tokens'] if t.gold]),
		} for fileid, file in files.items()]
		return json.jsonify(fileindex)

	@app.route('/<fileid>/tokens.json')
	def tokens(fileid):
		tokenindex = [{
			'info_url': url_for('tokeninfo', fileid=fileid, index=n),
			'image_url': url_for('tokenimage', fileid=fileid, index=n),
			'has_gold': (token.gold is not None and token.gold.strip() != ''),
		} for n, token in enumerate(files[fileid]['tokens'])]
		return json.jsonify(tokenindex)

	@app.route('/<fileid>/token-<int:index>.json', methods=['GET', 'POST'])
	def tokeninfo(fileid, index):
		token = files[fileid]['tokens'][index]
		if 'gold' in request.form:
			# NB: only works in singlethread/-process environs
			token.gold = request.form['gold']
			app.logger.debug(f'Received new gold for token: {token}')
			FileIO.save(files[fileid]['tokens'], workspace.paths[fileid].correctedTokenFile)
		return json.jsonify(vars(token))

	@app.route('/<fileid>/token-<int:index>.png')
	def tokenimage(fileid, index):
		token: PDFToken = files[fileid]['tokens'][index]
		(filename, image) = token.extract_image(workspace)
		with io.BytesIO() as output:
			image.save(output, format="PNG")
			return Response(output.getvalue(), mimetype='image/png')

	return app

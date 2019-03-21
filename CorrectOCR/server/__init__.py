import io

from flask import Flask, Response, json, url_for

from .. import progname
from ..tokens._pdf import PDFToken
from ..workspace import Workspace


def create_app(workspace: Workspace, config):
	# create and configure the app
	app = Flask(progname,
		instance_path=workspace.root,
	)
	app.config.from_mapping(
		SECRET_KEY='dev',
	)

	@app.route('/')
	def index():
		fileindex = [{
			'fileid': fileid,
			'url': url_for('tokens', fileid=fileid),
		} for fileid in workspace.paths if workspace.paths[fileid].ext == '.pdf']
		return json.jsonify(fileindex)

	@app.route('/<fileid>/tokens/')
	def tokens(fileid):
		tokenindex = [{
			'token': n,
			'url': url_for('tokeninfo', fileid=fileid, index=n),
		} for (n, t) in enumerate(workspace.binnedTokens(fileid))]
		return json.jsonify(tokenindex)

	@app.route('/<fileid>/token/<int:index>/')
	def tokeninfo(fileid, index):
		token = workspace.binnedTokens(fileid)[index]
		tokeninfo = {
			'token': vars(token),
			'image_url': url_for('tokenimage', fileid=fileid, index=index),
		}
		return json.jsonify(tokeninfo)

	@app.route('/<fileid>/image/<int:index>.png')
	def tokenimage(fileid, index):
		token: PDFToken = workspace.binnedTokens(fileid)[index]
		(filename, image) = token.extract_image(workspace)
		with io.BytesIO() as output:
			image.save(output, format="PNG")
			return Response(output.getvalue(), mimetype='image/png')

	return app

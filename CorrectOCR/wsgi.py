from .__main__ import setup
from .server import create_app
	
workspace, config, args = setup(['uwsgi.ini'], args=['server', '--loglevel', 'DEBUG'])

app = create_app(workspace, args)

if __name__ == "__main__":
	app.run()
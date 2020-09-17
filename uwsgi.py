from CorrectOCR.__main__ import setup
from CorrectOCR.server import create_app

workspace, args = setup(['CorrectOCR.ini'], args=['server', '--loglevel', 'DEBUG'])

app = create_app(workspace, args)

if __name__ == "__main__":
	app.run()

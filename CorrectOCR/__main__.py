import sys

from .config import setup

if __name__ == "__main__":
	ws, a = setup(['CorrectOCR.ini'], sys.argv[1:])

	a.func(ws, a)

	exit()

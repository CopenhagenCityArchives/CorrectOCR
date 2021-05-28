import sys

from .config import setup

if __name__ == "__main__":
	workspace, config = setup(sys.argv[1:])

	config.func(workspace, config)

	exit()

import csv
import json
import logging
import pickle
import shutil
from pathlib import Path
from typing import Any, List

from bs4.dammit import UnicodeDammit

from ._codecs import COCRJSONCodec
from .tokens.list import TokenList


def _open_for_reading(file: Path, binary=False):
	if binary:
		return open(str(file), 'rb')
	else:
		return open(str(file), 'r', encoding=FileIO.get_encoding(file))


##########################################################################################


class FileIO(object):
	"""
	Various file IO helper methods.
	"""
	log = logging.getLogger(f'{__name__}.FileIO')

	@classmethod
	def cachePath(cls, name: str = ''):
		path = Path('./__COCRcache__/').joinpath(f'{name}/')
		cls.ensure_directories(path)
		return path

	@classmethod
	def _csv_header(cls, kind: str, k: int) -> List[str]:
		header = ['Original']
		if kind in {'.alignedTokens', '.kbestTokens', '.binnedTokens', '.correctedTokens'}:
			header = ['Gold'] + header
		if kind in {'.kbestTokens', '.binnedTokens', '.correctedTokens'}:
			for n in range(1, k+1):
				header += [f'{n}-best', f'{n}-best prob.']
		if kind in {'.binnedTokens', '.correctedTokens'}:
			header += ['Bin', 'Heuristic', 'Decision', 'Selection']
		header += ['Token type', 'Token info', 'File ID', 'Index']
		cls.log.debug(f'header for {kind} k={k}: {header}')
		return header

	@classmethod
	def get_encoding(cls, file: Path) -> str:
		"""
		Get encoding of a text file.

		:param file: A path to a text file.
		:return: The encoding of the file, eg. 'utf-8', 'Windows-1252', etc.
		"""
		with open(str(file), 'rb') as f:
			dammit = UnicodeDammit(f.read(1024*500), ['utf-8', 'Windows-1252'])
			cls.log.debug(f'detected {dammit.original_encoding} for {file}')
			return dammit.original_encoding

	@classmethod
	def ensure_new_file(cls, path: Path):
		"""
		Moves a possible existing file out of the way by adding a numeric counter before the extension.

		:param path: The path to check.
		"""
		counter = 0
		originalpath = path
		while Path(path).is_file():
			path = Path(
				path.parent,
				f'{originalpath.stem}.{counter:03n}{originalpath.suffix}'
			)
			counter += 1
		if counter > 0:
			cls.log.info(f'Existing file moved to {path}')
			originalpath.rename(path)

	@classmethod
	def ensure_directories(cls, path: Path):
		"""
		Ensures that the entire path exists.

		:param path: The path to check.
		"""
		path.mkdir(parents=True, exist_ok=True)

	@classmethod
	def copy(cls, src: Path, dest: Path):
		"""
		Copies a file.

		:param src: Source-path.
		:param dest: Destination-path.
		"""
		cls.log.info(f'Copying {src} to {dest}')
		shutil.copy(str(src), str(dest))

	@classmethod
	def delete(cls, path: Path):
		"""
		Deletes a file.

		:param path: The path to delete.
		"""
		if path.exists():
			path.unlink()

	@classmethod
	def save(cls, data: Any, path: Path, backup=True):
		"""
		Saves data into a file. The extension determines the method of saving:

		-  `.pickle` -- uses :mod:`pickle`.
		-  `.json` -- uses :mod:`json`.
		-  `.csv` -- uses :class:`csv.DictWriter` (assumes data is list of :func:`vars()`-capable
		   objects). The keys of the first object determines the header.

		Any other extension will simply :func:`write()` the data to the file.

		:param data: The data to save.
		:param path: The path to save to.
		:param backup: Whether to move existing files out of the way via :meth:`ensure_new_file`
		"""
		binary = False
		if path.suffix == '.pickle':
			binary = True
		if backup:
			cls.ensure_new_file(path)
		if binary:
			def fopen():
				return open(str(path), 'wb')
		else:
			def fopen():
				return open(str(path), 'w', encoding='utf-8')
		with fopen() as f:
			if path.suffix == '.pickle':
				pickle.dump(data, f)
			elif path.suffix == '.json':
				json.dump(data, f, cls=COCRJSONCodec)
			elif path.suffix == '.csv':
				if isinstance(data, TokenList):
					header = cls._csv_header(path.suffixes[0], data[0].k)
					rows = [vars(x) for x in data]
				else:
					header = data[0].keys()
					rows = data
				writer = csv.DictWriter(f, header, delimiter='\t', extrasaction='ignore')
				writer.writeheader()
				writer.writerows(rows)
			else:
				f.write(data)

	@classmethod
	def load(cls, path: Path, default=None):
		"""
		Loads data from a file. The extension determines the method of saving:

		-  `.pickle` -- uses :mod:`pickle`.
		-  `.json` -- uses :mod:`json`.
		-  `.csv` -- uses :class:`csv.DictReader`.

		Any other extension will simply :func:`read()` the data from the file.

		:param path: The path to load from.
		:param default: If file doesn't exist, return default instead.
		:return: The data from the file, or the default.
		"""
		binary = False
		if path.suffix == '.pickle':
			binary = True
		if not path.is_file():
			return default
		with _open_for_reading(path, binary=binary) as f:
			if path.suffix == '.pickle':
				return pickle.load(f)
			elif path.suffix == '.json':
				return json.load(f, object_hook=COCRJSONCodec.object_hook)
			elif path.suffix == '.csv':
				return list(csv.DictReader(f, delimiter='\t'))
			else:
				return f.read()


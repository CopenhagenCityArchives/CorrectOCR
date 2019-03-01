import csv
import json
import logging
import pickle
import shutil
from pathlib import Path
from typing import Any, Dict, List

from bs4.dammit import UnicodeDammit

from .codecs import COCRJSONCodec


def open_for_reading(file: Path, binary=False):
	if binary:
		return open(str(file), 'rb')
	else:
		return open(str(file), 'r', encoding=FileIO.get_encoding(file))


##########################################################################################


class FileIO(object):
	log = logging.getLogger(f'{__name__}.FileIO')

	TOKENHEADER = ['Original', '1-best', '1-best prob.', '2-best', '2-best prob.', 
				   '3-best', '3-best prob.', '4-best', '4-best prob.', 
				   'Token type', 'Token info']
	GOLDHEADER = ['Gold'] + TOKENHEADER
	BINNEDHEADER = GOLDHEADER + ['Bin', 'Heuristic', 'Decision', 'Selection']

	headers: Dict[str, List[str]] = {
		'.tokens': TOKENHEADER,
		'.goldTokens': GOLDHEADER,
		'.binnedTokens': BINNEDHEADER,
	}

	@classmethod
	def get_encoding(cls, file: Path) -> str:
		with open(str(file), 'rb') as f:
			dammit = UnicodeDammit(f.read(1024*500), ['utf-8', 'Windows-1252'])
			cls.log.debug(f'detected {dammit.original_encoding} for {file}')
			return dammit.original_encoding

	@classmethod
	def ensure_new_file(cls, path: Path):
		counter = 0
		originalpath = path
		while Path(path).is_file():
			path = Path(
				path.parent,
				f'{originalpath.stem}.{counter:03n}{originalpath.suffix}'
			)
			counter += 1
		if counter > 0:
			logging.getLogger(f'{__name__}.ensure_new_file').info(f'Existing file moved to {path}')
			originalpath.rename(path)

	@classmethod
	def ensure_directories(cls, path):
		#if not path.parent.exists():
		#	
		#else:
		#	path.parent.mkdir()
		pass # TODO

	@classmethod
	def copy(cls, src: Path, dest: Path):
		cls.log.info(f'Copying {src} to {dest}')
		shutil.copy(str(src), str(dest))

	@classmethod
	def save(cls, data: Any, path: Path, binary=False, backup=True):
		if path.suffix == '.pickle':
			binary = True
		if backup:
			cls.ensure_new_file(path)
		if binary:
			fopen = lambda: open(str(path), 'wb')
		else:
			fopen = lambda: open(str(path), 'w', encoding='utf-8')
		with fopen() as f:
			if path.suffix == '.pickle':
				return pickle.dump(data, f)
			if path.suffix == '.json':
				return json.dump(data, f, cls=COCRJSONCodec)
			elif path.suffix == '.csv':
				header = cls.headers[path.suffixes[0]]
				writer = csv.DictWriter(f, header, delimiter='\t', extrasaction='ignore')
				writer.writeheader()
				return writer.writerows(data)
			else:
				return f.write(data)

	@classmethod
	def load(cls, path: Path, binary=False, default=None):
		if path.suffix == '.pickle':
			binary = True
		if not path.is_file():
			return default
		with open_for_reading(path, binary=binary) as f:
			if path.suffix == '.pickle':
				return pickle.load(f)
			if path.suffix == '.json':
				return json.load(f, object_hook=COCRJSONCodec.object_hook)
			elif path.suffix == '.csv':
				return list(csv.DictReader(f, delimiter='\t'))
			else:
				return f.read()


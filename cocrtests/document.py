import unittest

from .mocks import *

from CorrectOCR.document import Document


class TestDocument(unittest.TestCase):
	def __WIP__test_init(self):
		f = pathlib.Path(__file__).parent.joinpath('test.pdf')
		d = Document(MockWorkspace(), f)
		
		self.assertEqual(True, False, f'blah')

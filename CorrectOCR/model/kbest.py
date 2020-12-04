from dataclasses import dataclass

from ._util import punctuation_splitter

@dataclass
class KBestItem:
	candidate: str = ''
	probability: float = 0.0

	def __repr__(self) -> str:
		return f'<KBestItem {self.candidate}, {self.probability:.2e}>'

	@property
	def normalized(self):
		return punctuation_splitter(self.candidate)[1]

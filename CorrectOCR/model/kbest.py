from dataclasses import dataclass


@dataclass
class KBestItem:
	candidate: str = ''
	probability: float = 0.0

	def __repr__(self) -> str:
		return f'<KBestItem {self.candidate}, {self.probability:.2e}>'

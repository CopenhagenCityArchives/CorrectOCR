from dataclasses import dataclass

from dataclasses_json import dataclass_json

@dataclass_json
@dataclass
class KBestItem:
	candidate: str = ''
	probability: float = 0.0

	def __repr__(self) -> str:
		return f'<KBestItem {self.candidate}, {self.probability:.2e}>'

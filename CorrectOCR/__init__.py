from collections import deque
from typing import List, Iterator, TypeVar, Tuple

import regex


punctuationRE = regex.compile(r'\p{punct}+')


T = TypeVar('T')
def split_window(l: List[T], before=3, after=3) -> Iterator[Tuple[List[T], T, List[T]]]:
	a = deque(maxlen=before)
	for i in range(len(l)):
		yield list(a), l[i], l[i+1:i+1+after]
		a.append(l[i])

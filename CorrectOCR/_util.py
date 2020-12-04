import regex

punctuationRE = regex.compile(r'\p{punct}+')

_punctuation_splitter = regex.compile(r'^(\p{punct}*)(.*?)(\p{punct}*)$')

def punctuation_splitter(s):
	m = _punctuation_splitter.search(s)
	return m.groups('')

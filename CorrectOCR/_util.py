import regex

punctuationRE = regex.compile(r'\p{punct}+')

hyphenRE = regex.compile(r'(?:\{Pd}|[\xad\-])+$')

letterRE = regex.compile(r'\p{L}')

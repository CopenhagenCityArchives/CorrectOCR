#!/usr/bin/env python

import os, sys
import json
import regex, re
import csv
from collections import defaultdict

#nonword = regex.compile(r'^[\p{space}\p{punct}\\]$')
nonword = re.compile(r'\W+')

corrections = dict()

for filename in sys.argv[2:]: # from train/parallelAligned/fullAlignments
	print(filename)
	
	alignments = None
	with open(filename, encoding='utf-8') as f:
		alignments = json.load(f)
	
	pair = ["", ""]
	for a in alignments:
		if nonword.match(a[0]) or nonword.match(a[1]):
			if pair[0] != pair[1]:
				print(pair)
				corrections[pair[0]] = pair[1]
			pair = ["", ""]
		else:
			pair[0] += a[0]
			pair[1] += a[1]

print(corrections)
print(len(corrections))

reader = csv.DictReader(open(sys.argv[1], encoding='utf-8'), lineterminator='\n', delimiter='\t', quoting=csv.QUOTE_NONE, quotechar='')

header = ['Gold'] + reader.fieldnames

outfile = open('train/devDecoded/%d.csv' % len(corrections), 'w', encoding='utf-8')
out = csv.DictWriter(outfile, header, lineterminator='\n', delimiter='\t', quoting=csv.QUOTE_NONE, quotechar='', extrasaction='ignore')
out.writeheader()

for row in reader:
	row['Gold'] = corrections.get(row['Original'], row['Original'])
	try:
		out.writerow(row)
	except:
		print(row)
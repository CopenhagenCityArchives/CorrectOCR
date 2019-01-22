import regex
import logging

class Heuristics(object):
	def __init__(self, dictionary, heuristicSettings):
		self.dictionary = dictionary
		self.heuristicSettings = heuristicSettings
		self.punctuation = regex.compile(r'\p{posix_punct}+')
		self.log = logging.getLogger(__name__+'.Heuristics')
	
	def evaluate(self, token, dcode):
		# original form
		original = self.punctuation.sub('', token['Original'])
		
		# top k best
		k1 = token['1-best']
		
		# evaluate candidates against the dictionary
		
		oind = self.dictionary.contains(original) #orig in dict?
		k1ind = self.dictionary.contains(k1) #k1 in dict?
		
		if ((original == k1) & oind):
			# k1 = orig and this is in dict.
			bin = 1
		elif ((original == k1) & (not oind)) & (dcode == 'zerokd'):
			# k1 = orig but not in dict, and no other kbest in dict either
			bin = 2
		elif ((original == k1) & (not oind)) & (dcode == 'somekd'):
			# k1 = orig but not in dict, but some lower-ranked kbest is in dict
			bin = 3
		elif ((original != k1) & (not oind)) & k1ind:
			# k1 is different from orig, and k1 passes dict check while orig doesn't
			bin = 4
		elif ((original != k1) & (not oind)) & (dcode == 'zerokd'):
			# k1 is different from orig and nothing anywhere passes dict check
			bin = 5
		elif ((original != k1) & (not oind)) & ((not k1ind) & (dcode == 'somekd')):
			# k1 is different from orig and neither is in dict,
			# but a lower-ranked candidate is
			bin = 6
		elif ((original != k1) & oind) & k1ind:
			# k1 is different from orig and both are in dict
			bin = 7
		elif ((original != k1) & oind) & (dcode == 'zerokd'):
			# k1 is different from orig, orig is in dict and no candidates are in dict
			bin = 8
		elif ((original != k1) & oind) & ((not k1ind) & (dcode == 'somekd')):
			# k1 is different from orig, k1 not in dict but a lower candidate is
			#   and orig also in dict
			bin = 9
		else:
			self.log.critical("This shouldn't happen!")
			bin = 0
		
		return (bin, self.heuristicSettings.get(bin, None))

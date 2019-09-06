Ideas for future features
=========================

tokenizer
---------
Option for squishing abbreviations into single tokens?

```python
mwes = [
	('P', 'E'), # Politiets Efterretninger
	('d', 'M'), # denne Maaned
	('s', 'M'), # samme Maaned
	('f', 'M'), # forrige Maaned
]
mwe = nltk.tokenize.MWETokenizer(mwes, separator='.')
words = mwe.tokenize(words)
```

Alternately, create an `AbbreviationToken` that holds the constituent parts similar to DehyphenationToken and where gold is the expanded abbreviation.


hocr
----

*	improve page segmentation/layout analysis
	*	https://www.slideshare.net/MarkHollow/pycon-apac-2017-page-layout-analysis-of-19th-century-siamese-newspapers-using-python-and-opencv
	*	https://www.danvk.org/2015/01/07/finding-blocks-of-text-in-an-image-using-python-opencv-and-numpy.html
		*	https://github.com/danvk/oldnyc/blob/master/ocr/tess/crop_morphology.py
		*	https://gist.github.com/luipillmann/d76eb4f4eea0320bb35dcd1b2a4575ee
	*	https://github.com/glazzara/olena
	*	https://github.com/phatn/lapdftext


dictionary
----------

consider word frequency and weight lookups accordingly? 


misc
----

*	https://info.clarin.dk/
*	http://sprogtek2018.dk/
*	https://alf.hum.ku.dk/korp/?mode=da1800
*	https://clarin.dk/clarindk/find.jsp

Transkribus
-----------

* Look into integrating with the python client
	* https://github.com/Transkribus/TranskribusPyClient
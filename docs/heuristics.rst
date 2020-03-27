Heuristics
----------

A given token and its *k*-best candidates are compared and checked with
the dictionary. Based on this, it is matched with a *bin*.

============================== = = = = = = = = =
bin                            1 2 3 4 5 6 7 8 9
============================== = = = = = = = = =
*k* = orig?                    T T T F F F F F F
orig in dict?                  T F F F F F T T T
top *k*-best in dict?          T F F T F F T F F
lower-ranked *k*-best in dict? – F T – F T – F T
============================== = = = = = = = = =

Each *bin* must be assigned a setting that determines what decision is
made:

-  ``o`` / *original*: select the original token as correct.
-  ``k`` / *kbest*: select the top *k*-best candidate as correct.
-  ``d`` / *kdict*: select the first lower-ranked candidate that is in
   the dictionary.
-  ``a`` / *annotator*: defer selection to annotator.

Once the report and settings are generated, it is not strictly necessary
to update them every single time the model is updated. It is however a
good idea to do it regularly as the corpus grows and more tokens become
available for the statistics.
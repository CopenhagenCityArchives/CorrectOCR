Correction Interface
--------------------

The annotator will be presented with the tokens that match a heuristic
bin that was marked for annotation.

They may then enter a command. The commands reflect the above settings,
with an additional ``defer`` command to defer decision to a later time.

Prefixing the entered text with an exclamation point causes it to be
considered the corrected version of the token. For example, if the token
is “Wagor” and no suitable candidate is available, the annotator may
enter ``!Wagon`` to correct the word.

Corrections are memoized, so the file need not be corrected fully in one
session. To finish a session and save corrections, use the ``quit``
command.

A ``help`` command is available in the interface.


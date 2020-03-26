CorrectOCR.server module
========================

Below are some examples for a possible frontend. Naturally, they are only
suggestions and any workflow and interface may be used.

Example Workflow
----------------

.. uml:: CorrectOCR.server.api.puml

Open the image in a new window to view at size.

Example User Interface
----------------------

.. uml:: CorrectOCR.server.gui.puml

The Combo box would then contain the `k`-best suggestions from the backend,
allowing the user to accept the desired one or enter their own correction.

Showing the left and right tokens (ie. tokens with index±1) enables to user
to decide if a token is part of a longer word that should be hyphenated.

Endpoint Documentation
----------------------

Errors are specified according to `RFC 7807 Problem Details for HTTP APIs <https://tools.ietf.org/html/rfc7807>`_.

.. qrefflask:: CorrectOCR.server:create_app()
   :undoc-static:

.. autoflask:: CorrectOCR.server:create_app()
   :endpoints:
   :order: path
   :undoc-static:

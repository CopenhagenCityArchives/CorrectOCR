CorrectOCR.server module
========================

Below are some examples for a possible frontend. Naturally, they are only
suggestions and any workflow and interface may be used.

Example Workflow
----------------

.. uml:: CorrectOCR.server.api.uml

Example User Interface
----------------------

.. uml:: CorrectOCR.server.gui.uml

The Combo box would then contain the `k`-best suggestions from the backend,
allowing the user to accept the desired one or enter their own correction.

Showing the left and right tokens (ie. tokens with index±1) is for
hyphenation TODO

Endpoint Documentation
----------------------

.. qrefflask:: CorrectOCR.server:create_app()
   :undoc-static:

.. autoflask:: CorrectOCR.server:create_app()
   :endpoints:
   :order: path
   :undoc-static:

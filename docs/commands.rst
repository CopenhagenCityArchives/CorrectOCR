Commands
========

Global Arguments
----------------

If the global arguments are not provided on the command line, `CorrectOCR.ini` and environment variables are checked (see :doc:`configuration`).

Workspace
^^^^^^^^^

.. argparse ::
   :ref: CorrectOCR.cli.get_workspace_argparser
   :prog: python -m CorrectOCR

   These arguments configure the :class:`Workspace<CorrectOCR.workspace.Workspace>`, ie. where the documents are located.
   
Resource
^^^^^^^^

.. argparse ::
   :ref: CorrectOCR.cli.get_resource_argparser
   :prog: python -m CorrectOCR

   These arguments configure the :class:`ResourceManager<CorrectOCR.workspace.ResourceManager>`, eg. dictionary, model, etc.

Storage
^^^^^^^

.. argparse ::
   :ref: CorrectOCR.cli.get_storage_argparser
   :prog: python -m CorrectOCR

   These arguments configure the :class:`TokenList<CorrectOCR.tokens.list.TokenList>` backend storage.

Commands
--------

.. argparse ::
   :ref: CorrectOCR.cli.get_root_argparser
   :prog: python -m CorrectOCR


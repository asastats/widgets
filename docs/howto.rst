Howto
=====

Add content
-----------

Add your content using ``reStructuredText`` syntax. See the
`reStructuredText <https://www.sphinx-doc.org/en/master/usage/restructuredtext/index.html>`_
documentation for details.


Create documentation
--------------------

Activate the project's Python environment and create the documentation by invoking a simple `make` command:

.. code-block:: bash

    cd docs
    make html
    # make latexpdf

The created docs are placed in the `docs/_build` directory.

The documentation of this project is created and hosted automatically through the
`Read the Docs <https://about.readthedocs.com>`_ platform.

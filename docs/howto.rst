Howto
=====

Build the documentation
-----------------------

Pages are `reStructuredText <https://www.sphinx-doc.org/en/master/usage/restructuredtext/index.html>`_.
Activate the project's Python environment and run:

.. code-block:: bash

    cd docs
    make html
    # make latexpdf

The output is in ``docs/_build``. Read the Docs builds and hosts the documentation
automatically.

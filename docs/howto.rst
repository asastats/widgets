Howto
=====

Setup development Python environment
------------------------------------

Run `python -m venv asa` and add the following lines to the end of related file:

.. code-block:: bash
  :caption: asa/bin/activate

  export DJANGO_SETTINGS_MODULE=asastats.settings.development
  export SECRET_KEY="mysecretkey"

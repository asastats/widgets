About
=====

Introduction
------------

This repository includes the code for all 
`ASA Stats user widgets <https://github.com/asastats/channel/wiki/User-Widgets>`_.

The first published user widget - historic data widget - will serve as the basis for developing all subsequent user widgets.

The main structure represents a 
`Django app <https://www.djangoproject.com/>`_
that is imported into ASA Stats' main repository as a
`Git submodule <https://git-scm.com/book/en/v2/Git-Tools-Submodules>`_.


Structure
---------

This repository contains the base code that is common to all the user widgets, as well as two main directories/packages where the code for published widgets will reside.

.. code-block:: bash

    widgets/
    ├── docs/
    ├── inhouse/
    │   └── historic/...
    ├── migrations/
    ├── static/
    ├── templates/
    ├── tests/
    └── thirdparty/


The ASA Stats community has been collecting and filtering user requests for widgets since day one.
It is expected that all of
`those requests <https://github.com/asastats/channel/wiki/FeaturesDependentOnUserWidgets>`_
eventually end up in a form of user widgets, with the code that resides in this repository.


Inhouse
^^^^^^^

The `inhouse` directory contains the user widgets developed by the ASA Stats team.


Thirdparty
^^^^^^^^^^

The `thirdparty` directory contains the user widgets developed by other developers.
All the widgets from this directory have to be approved by the ASA Stats team
before they are published on the ASA Stats website.

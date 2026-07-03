Development
===========

Setup
-----

Python environment
^^^^^^^^^^^^^^^^^^

Create Python virtual environment:

.. code-block:: bash

  python3 -m venv widgets


Activate Python environment:

.. code-block:: bash

  source widgets/bin/activate


Adding an alias can be useful:

.. code-block:: bash
  :caption: ~/.bashrc

  alias 'widgets'='cd /home/ipaleka/dev/widgets; \
    source /home/ipaleka/dev/venvs/widgets/bin/activate'


SonarQube
^^^^^^^^^

`SonarQube <https://docs.sonarsource.com/sonarqube-community-build>`_
is an automated code review and static analysis tool designed to detect coding issues.
You can find the installation instructions
`here <https://docs.sonarsource.com/sonarqube-community-build/try-out-sonarqube>`


Starting server
"""""""""""""""

.. code-block:: bash

  $ ~/opt/repos/sonarqube-9.4.0/bin/linux-x86-64/sonar.sh console


Starting scanner
""""""""""""""""

You should add scanner executable to your PATH. For example, by adding the following
line to your ``~/.bashrc``:

.. code-block:: bash

  export PATH=$PATH:~/opt/repos/sonar-scanner/bin


To start scanning, run the scanner from the root directory of the project with:

.. code-block:: bash

  $ sonar-scanner


Newer versions require authentication:

.. code-block:: bash

  $ sonar-scanner -Dsonar.login=admin -Dsonar.password=password -Dsonar.projectKey=user-widgets


For additional information read the scanner `documentation`_.

.. _documentation: https://docs.sonarqube.org/latest/analysis/scan/sonarscanner/


Tests
-----

Python
^^^^^^

The Python tests for this repository are executed directly by the parent "frontend"
repository's CI/CD workflow, where this code is included as a submodule.


Javascript
^^^^^^^^^^

System wide `nodejs` and `npm` should be installed:

.. code-block:: bash

  apt-get install nodejs npm


Install project's Node dependencies with:

.. code-block:: bash

  cd /home/ipaleka/dev/widgets/
  npm install


Install jest globally:

.. code-block:: bash

  npm install -g jest


Run project's Javascript tests with:

.. code-block:: bash

  cd /home/ipaleka/dev/widgets/
  jest


Creating a widget
-----------------

Before writing any code, read :file:`WIDGET_CONTRACT.md` in this directory. It is the
authoritative description of the widget model and the rules the publication audit
enforces; building out of step with it (assuming a widget may read the ORM directly, or
naming an engine endpoint after the widget) means rework. The essentials:

- **Two manifest axes.** ``origin`` (``inhouse`` | ``thirdparty``) is provenance only;
  ``capability`` (``public`` | ``engine-backed``) decides whether the widget may call the
  privileged engine endpoints it declares. A ``public`` widget declares no
  ``engine_endpoints``; an ``engine-backed`` one must declare each, and every one must be
  a subset of the deployment token's scopes.
- **Generic engine scopes.** Engine endpoints are named after the data
  (``account:holdings``, ``assets:lookup``), never after the widget, so a scope is shared
  across widgets.
- **Declare a limit, check a limit.** Any per-widget resource ceiling the widget relies
  on (e.g. ``max_addresses``) must be both declared in ``limits`` and enforced by the
  widget's own engine endpoints. Absence of a configured limit denies.
- **The widget owns its wiring.** A widget keeps its own ``urls.py`` and ``routing.py``;
  templates and static files are found through Django's normal app discovery. The
  manifest carries metadata and grants only — no routes, consumers, menu, or asset paths.
- **Conventions.** Follow the test and docstring conventions already in ``inhouse``:
  ``Test<CamelPath><Thing>`` classes, ``mocker`` fixtures without method docstrings,
  Sphinx ``:param:``/``:type:`` field lists, and the jsdom harness for JavaScript. The
  ``historic`` widget is the worked example to copy.


Realtime
^^^^^^^^

An engine-backed widget's live updates travel over a shared Channels-Redis bus: the
engine workers ``group_send`` and the widget's open consumer relays to the browser. Two
rules keep it working:

- **One Redis, both sides.** The engine and the frontend must point their Channels layer
  at the *same* Redis host, port, and database; the bundle group name is vendored into
  the widget so both resolve it identically. A port or database mismatch lets the
  handshake succeed while no message ever arrives.
- **One htmx per page.** The host loads htmx once; a widget ships only the extensions it
  needs (e.g. ``htmx-ext-ws``), never its own htmx core. A second htmx on the page
  silently drops ``ws-connect`` and no socket opens.

Pin ``channels``, ``channels_redis`` and ``redis`` to a tested set — a newer ``redis-py``
(RESP3) against an older ``channels_redis`` surfaces as a read timeout on the bus.


Engine data contract
^^^^^^^^^^^^^^^^^^^^^

An engine-backed widget receives render-ready JSON, not Python objects. Namedtuples
serialise to JSON arrays, so the engine emits **keyed** dicts and the widget rebuilds them
into its display structs at the boundary — by field name, tolerant of a missing or added
field. Pin the shape with a small golden-fixture test so a rename on either side fails a
test rather than a page. See ``inhouse.historic`` for the pattern.


Deployment (administrator steps)
--------------------------------

A finished widget does not run until an ASA Stats administrator publishes it. As a widget
developer, expect these steps and supply what they need:

#. **Register the id.** Add the widget id to ``INHOUSE_WIDGETS`` (or
   ``THIRDPARTY_WIDGETS``, by ``origin``) in **both** ``widgets/constants.py`` and the
   frontend's ``config/settings/base.py``. The two lists must agree, or ``reverse()`` on
   the widget's URL raises ``NoReverseMatch`` and its entry renders empty.

   .. code-block:: python

     # widgets/constants.py  AND  frontend/website/config/settings/base.py
     INHOUSE_WIDGETS = ["historic", "folks", "haystack", "swapcore"]
     THIRDPARTY_WIDGETS = []

#. **Grant the engine token (engine-backed widgets).** The widget's ``engine_endpoints``
   must be present in the deployment token's ``scopes``, and every per-widget limit the
   widget checks must be set in the token's ``limits`` — an absent limit denies. These live
   on the engine; a fork without the grant cannot run the widget.
#. **Provide host settings.** Any settings the widget reads from the host (external API
   keys, referrer addresses, and — where a widget is not a full Django app — its static and
   template directories) go into the frontend configuration. List them in the widget's own
   README (and runbook) so the administrator can set them.
#. **Audit.** Publication verifies the code stays within what the manifest declares (see
   :doc:`widget_contract`).
#. **Restart.** Restart the frontend, and for realtime widgets the engine workers, so the
   new URLconf, routing and registry are loaded.

For realtime widgets, also confirm the engine and frontend share one Channels-Redis
endpoint (see `Realtime`_ above). Widget-specific operational procedures — enabling a
referrer, claiming fees, and the like — belong in that widget's runbook (see
:doc:`runbooks`).

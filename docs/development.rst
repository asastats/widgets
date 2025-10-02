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

.. code-block:: bash

  cd /home/ipaleka/dev/widgets
  source /home/ipaleka/dev/venvs/widgets/bin/activate
  python -m pytest -v


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


Widgets
=======

Symlinks
--------

We need to add to Ansible playbook symlink creation for all published widgets.

In-house widgets represent those developed by the ASA Stats Team.


Templates
^^^^^^^^^

.. code-block:: bash

  ln -sf /home/ipaleka/dev/asastats_repo/asastats/widgets/inhouse/historic/templates/historic/ \
    /home/ipaleka/dev/asastats_repo/asastats/widgets/templates/historic


Static files
^^^^^^^^^^^^

.. code-block:: bash

  ln -sf /home/ipaleka/dev/asastats_repo/asastats/widgets/inhouse/historic/static/historic/ \
    /home/ipaleka/dev/asastats_repo/asastats/widgets/static/historic


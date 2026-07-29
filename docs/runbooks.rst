Runbooks
========

Operational runbooks for individual widgets — the procedures an operator or administrator
follows to configure and run a *specific* widget (enabling a referrer, claiming fees, and
so on), as opposed to the shared rules in :doc:`widget_contract` or the build steps in
:doc:`development`.

Convention: a widget that has operator-facing procedures ships its runbook **alongside its
code** at ``inhouse/<widget>/runbook.rst``, so it is versioned and audited with the widget
(this matters especially for ``thirdparty`` widgets, which bring their own). Each page
below is a one-line stub that ``.. include::``\ s the widget's runbook, keeping the source
of truth next to the code while still rendering here.

A runbook is short and covers, in order: **Configuration** (host settings the widget
reads), **Operations** (procedures the administrator runs), and **Links**. Anything
generic belongs in :doc:`development` or :doc:`widget_contract` instead.

.. toctree::
   :maxdepth: 1

   runbooks/asastats
   runbooks/folks
   runbooks/haystack

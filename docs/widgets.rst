:mod:`widgets.inhouse` -- User widgets developed by ASA Stats
*************************************************************

.. automodule:: inhouse
  :members:
  :undoc-members:
  :show-inheritance:


.. The alerts directives below are the only ones addressed as
   ``widgets.inhouse.alerts.*`` rather than flat ``inhouse.*``, and they have to
   be. This is the one widget that defines Django models, and the app registry
   knows them by the path INSTALLED_APPS named - ``widgets``. Imported flat, the
   same file is executed a second time under a second module name, and
   ``ModelBase`` rejects the class: "doesn't declare an explicit app_label and
   isn't in an application in INSTALLED_APPS".

:mod:`widgets.inhouse.alerts` -- Alerts widget package
--------------------------------------------------------

.. automodule:: widgets.inhouse.alerts
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.alerts.evaluate` -- Alerts widget's rule evaluation module
----------------------------------------------------------------------------------

.. automodule:: widgets.inhouse.alerts.evaluate
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.alerts.forms` -- Alerts widget's forms module
---------------------------------------------------------------------

.. automodule:: widgets.inhouse.alerts.forms
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.alerts.manifest` -- Alerts widget's manifest module
---------------------------------------------------------------------------

.. automodule:: widgets.inhouse.alerts.manifest
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.alerts.models` -- Alerts widget's rule store module
---------------------------------------------------------------------------

.. automodule:: widgets.inhouse.alerts.models
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.alerts.population` -- Alerts widget's engine population module
--------------------------------------------------------------------------------------

.. automodule:: widgets.inhouse.alerts.population
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.alerts.push` -- Alerts widget's web push delivery module
--------------------------------------------------------------------------------

.. automodule:: widgets.inhouse.alerts.push
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.alerts.tiers` -- Alerts widget's per-tier allowance module
----------------------------------------------------------------------------------

.. automodule:: widgets.inhouse.alerts.tiers
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.alerts.urls` -- Alerts widget's URL configurations module
---------------------------------------------------------------------------------

.. automodule:: widgets.inhouse.alerts.urls
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.alerts.views` -- Alerts widget's views module
---------------------------------------------------------------------

.. automodule:: widgets.inhouse.alerts.views
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.alerts.tests` -- Alerts widget's unit-tests package
---------------------------------------------------------------------------

.. automodule:: widgets.inhouse.alerts.tests
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.asastats` -- ASA Stats swap widget package (inherits swapcore)
------------------------------------------------------------------------------------

.. automodule:: inhouse.asastats
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.asastats.manifest` -- ASA Stats widget's manifest module
------------------------------------------------------------------------------

.. automodule:: inhouse.asastats.manifest
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.asastats.urls` -- ASA Stats widget's URL configurations module
------------------------------------------------------------------------------------

.. automodule:: inhouse.asastats.urls
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.asastats.views` -- ASA Stats widget's views module
------------------------------------------------------------------------

.. automodule:: inhouse.asastats.views
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.asastats.tests` -- ASA Stats widget's unit-tests package
------------------------------------------------------------------------------

.. automodule:: inhouse.asastats.tests
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.dustsweep` -- Dust Sweep widget package
--------------------------------------------------------------

.. automodule:: inhouse.dustsweep
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.dustsweep.manifest` -- Dust Sweep widget's manifest module
--------------------------------------------------------------------------------

.. automodule:: inhouse.dustsweep.manifest
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.dustsweep.urls` -- Dust Sweep widget's URL configurations module
---------------------------------------------------------------------------------------

.. automodule:: inhouse.dustsweep.urls
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.dustsweep.views` -- Dust Sweep widget's views module
---------------------------------------------------------------------------

.. automodule:: inhouse.dustsweep.views
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.dustsweep.tests` -- Dust Sweep widget's unit-tests package
---------------------------------------------------------------------------------

.. automodule:: inhouse.dustsweep.tests
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.folks` -- Folks swap widget package (inherits swapcore)
-----------------------------------------------------------------------------

.. automodule:: inhouse.folks
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.folks.manifest` -- Folks widget's manifest module
-----------------------------------------------------------------------

.. automodule:: inhouse.folks.manifest
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.folks.urls` -- Folks widget's URL configurations module
-----------------------------------------------------------------------------

.. automodule:: inhouse.folks.urls
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.folks.views` -- Folks widget's views module
-----------------------------------------------------------------

.. automodule:: inhouse.folks.views
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.folks.tests` -- Folks widget's unit-tests package
-----------------------------------------------------------------------

.. automodule:: inhouse.folks.tests
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.haystack` -- Haystack swap widget package (inherits swapcore)
-----------------------------------------------------------------------------------

.. automodule:: inhouse.haystack
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.haystack.manifest` -- Haystack widget's manifest module
-----------------------------------------------------------------------------

.. automodule:: inhouse.haystack.manifest
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.haystack.urls` -- Haystack widget's URL configurations module
-----------------------------------------------------------------------------------

.. automodule:: inhouse.haystack.urls
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.haystack.views` -- Haystack widget's views module
-----------------------------------------------------------------------

.. automodule:: inhouse.haystack.views
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.haystack.tests` -- Haystack widget's unit-tests package
-----------------------------------------------------------------------------

.. automodule:: inhouse.haystack.tests
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.historic` -- Historic widget's package
------------------------------------------------------------

.. automodule:: inhouse.historic
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.historic.charts` -- Historic widget's charts data creation module
---------------------------------------------------------------------------------------

.. automodule:: inhouse.historic.charts
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.historic.constants` -- Historic widget's constants module
-------------------------------------------------------------------------------

.. automodule:: inhouse.historic.constants
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.historic.consumers` -- Historic widget's websocket consumers module
-----------------------------------------------------------------------------------------

.. automodule:: inhouse.historic.consumers
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.historic.helpers` -- Historic widget's helpers module
---------------------------------------------------------------------------

.. automodule:: inhouse.historic.helpers
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.historic.manifest` -- Historic widget's manifest module
-----------------------------------------------------------------------------

.. automodule:: inhouse.historic.manifest
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.historic.routing` -- Historic widget's routes configuration module
----------------------------------------------------------------------------------------

.. automodule:: inhouse.historic.routing
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.historic.structs` -- Historic widget's data structures module
-----------------------------------------------------------------------------------

.. automodule:: inhouse.historic.structs
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.historic.urls` -- Historic widget's URL configurations module
-----------------------------------------------------------------------------------

.. automodule:: inhouse.historic.urls
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.historic.views` -- Historic widget's views module
-----------------------------------------------------------------------

.. automodule:: inhouse.historic.views
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.historic.wire` -- Historic widget's wire module
---------------------------------------------------------------------

.. automodule:: inhouse.historic.wire
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.historic.tests` -- Historic widget's unit-tests package
-----------------------------------------------------------------------------

.. automodule:: inhouse.historic.tests
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.hogswap` -- HOGSWAP swap widget package (inherits swapcore)
---------------------------------------------------------------------------------

.. automodule:: inhouse.hogswap
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.hogswap.manifest` -- HOGSWAP widget's manifest module
----------------------------------------------------------------------------

.. automodule:: inhouse.hogswap.manifest
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.hogswap.urls` -- HOGSWAP widget's URL configurations module
---------------------------------------------------------------------------------

.. automodule:: inhouse.hogswap.urls
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.hogswap.views` -- HOGSWAP widget's views module
----------------------------------------------------------------------

.. automodule:: inhouse.hogswap.views
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.hogswap.tests` -- HOGSWAP widget's unit-tests package
----------------------------------------------------------------------------

.. automodule:: inhouse.hogswap.tests
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.liverefresh` -- Real-time refresh widget package
------------------------------------------------------------------------

.. automodule:: inhouse.liverefresh
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.liverefresh.allowance` -- Real-time refresh widget's allowance module
---------------------------------------------------------------------------------------------

.. automodule:: inhouse.liverefresh.allowance
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.liverefresh.manifest` -- Real-time refresh widget's manifest module
-------------------------------------------------------------------------------------------

.. automodule:: inhouse.liverefresh.manifest
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.liverefresh.urls` -- Real-time refresh widget's URL configurations module
-------------------------------------------------------------------------------------------------

.. automodule:: inhouse.liverefresh.urls
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.liverefresh.views` -- Real-time refresh widget's views module
-------------------------------------------------------------------------------------

.. automodule:: inhouse.liverefresh.views
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.liverefresh.warmset` -- Real-time refresh widget's warm set module
------------------------------------------------------------------------------------------

.. automodule:: inhouse.liverefresh.warmset
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.liverefresh.tests` -- Real-time refresh widget's unit-tests package
-------------------------------------------------------------------------------------------

.. automodule:: inhouse.liverefresh.tests
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.swapcore` -- Abstract widget for swap/router widgets
--------------------------------------------------------------------------

.. automodule:: inhouse.swapcore
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.swapcore.manifest` -- Swapcore widget's manifest module
-----------------------------------------------------------------------------

.. automodule:: inhouse.swapcore.manifest
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.swapcore.urls` -- Swapcore widget's URL configurations module
-----------------------------------------------------------------------------------

.. automodule:: inhouse.swapcore.urls
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.swapcore.views` -- Swapcore widget's views module
-----------------------------------------------------------------------

.. automodule:: inhouse.swapcore.views
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.inhouse.swapcore.tests` -- Swapcore widget's unit-tests package
-----------------------------------------------------------------------------

.. automodule:: inhouse.swapcore.tests
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.apps` -- ASA Stats user widgets configuration module
******************************************************************

.. automodule:: apps
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.constants` -- ASA Stats user widgets system's constants module
****************************************************************************

.. automodule:: constants
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.routing` -- ASA Stats user widgets system's routes configuration module
*************************************************************************************

.. automodule:: routing
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.urls` -- ASA Stats user widgets system's URL configurations module
********************************************************************************

.. automodule:: urls
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.views` -- ASA Stats user widgets system's base views module
*************************************************************************

.. automodule:: views
  :members:
  :undoc-members:
  :show-inheritance:


:mod:`widgets.tests` -- ASA Stats user widgets system's unit-tests package
--------------------------------------------------------------------------

.. automodule:: tests
  :members:
  :undoc-members:
  :show-inheritance:

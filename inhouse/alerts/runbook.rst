======
Alerts
======

Rules a reader writes about prices and portfolio totals, evaluated against
numbers the engine's own loops already compute, delivered by web push.

State
=====

.. warning::

   **All four subjects are built. Configuration turns them on.**

   ``total_value``, ``asa_total`` and ``total_percent`` ride the live pass: the
   widget publishes a page into ``lvr``, the engine re-prices it and posts a
   signed trigger, and ``AlertsRepricedView`` evaluates and sends.
   ``asa_price`` rides a periodic huey task instead: the widget publishes asset
   ids into ``lvra``, the engine prices them every five minutes, and
   ``AlertsPricedView`` evaluates.

   It stays silent until ``ALERTS_WEBHOOK_SECRET`` is set **in both projects'**
   ``.env`` and ``ALERTS_WEBHOOK_URL`` in the engine's. An unset URL makes no
   call; a URL with no secret is refused by the receiver and logged by the
   sender. The modal says so, keyed on that secret. ``post-deploy/
   RUN-alerts-by-hand.md`` is the procedure - and price alerts additionally
   need the **huey consumer**, not just the transmitter.

Design
======

``notifications/DESIGN.md`` is the design and ``notifications/PREREQUISITES.md``
is what had to exist before it. This page does not repeat either. The three
things worth knowing before changing anything here:

**This widget holds no engine privilege.** ``capability = "public"``, no
``engine_endpoints``. A feature about live prices sounds engine-backed, and is
not: every row it reads and writes is in this deployment's own database, and the
numbers it compares them against are read from the Redis both projects already
share. Nothing here calls an engine endpoint.

**The website evaluates; the engine only says a page moved.** An earlier draft
had it the other way round. The rules belong to users and so live here, and so
does their fire state (``last_value``, ``last_fired_at``) - evaluating in the
engine would mean projecting both into Redis and giving one fact two owners,
which is how a rule comes to fire twice or never. So the engine's whole
contribution is a signed ``POST`` to ``AlertsRepricedView`` naming the page, and
``evaluate.py`` does the rest.

**There are two evaluators, not one.** ``total_value`` and ``asa_total`` ride on
numbers the live pass publishes per page per block, and ``evaluate.py`` reads
them. ``asa_price`` is not per-reader at all - it is per-asset, and belongs in a
pass that runs once per asset over the union named in active rules.
``total_percent`` needs a series rather than a reading and waits on that same
work. Both are named in ``evaluate.SKIPPED`` and counted rather than ignored;
treating all four as one evaluator is how this gets built twice.

**A rule fires on a crossing, not a level.** ``AlertRule.crossed`` returns true
only when the previous reading was on the other side of the threshold. A level
test notifies on every tick for as long as the value stays past the line, and an
asset oscillating around one notifies forever - which is how a reader comes to
turn the feature off rather than tune it. A rule that has never taken a reading
*arms*; it does not fire.

Where the table lives
=====================

In the ``widgets`` app, not this package, and not an app of its own.

Widgets are not Django apps. ``widgets`` is, and its ``migrations/`` package has
stood empty since it was created. Django resolves an app label by the longest
matching prefix in ``INSTALLED_APPS``, so a model declared in
``widgets/inhouse/alerts/models.py`` belongs to ``widgets`` and its migration
lands in ``widgets/migrations/``.

What Django will **not** do is import it. Only ``<app>/models.py`` is imported
at startup, so ``widgets/models.py`` names this widget's models and exists for
no other reason. **A widget that adds a model must add its import there or the
table is never created**, and the failure is a missing relation at runtime
rather than anything at import time.

The control
===========

Rendered by ``templates/_swap_entry.html``, the address page's one non-cached
per-reader partial - **not** by this widget's own view, and not by a second htmx
request.

``address.html`` is ``cache_page``'d across readers. How many rules *you* keep
is per-reader, so rendering it into that page lets whoever warms the entry
decide what every later reader sees. That is the 2026-09-13 Dust Sweep report,
and the sweep and the swap gate already live in this partial for the same
reason. A second partial would be a second request for a question this one has
already answered.

``core.views._alerts_allowance`` supplies the counts, and **imports this widget
inside the function**:

.. code-block:: python

   try:
       from widgets.inhouse.alerts.models import AlertRule
       from widgets.inhouse.alerts.tiers import rules_allowed
   except ImportError as error:
       logger.warning("alerts control unavailable: %s", error)
       return 0, 0

The widgets repo syncs separately from the frontend, so "the frontend is newer
than the widgets" is an ordinary state of the world for minutes at a time. A
module-level import made ``api.views`` unimportable on 2026-09-20 and 500'd
every page on the site. With the guard, a skew costs the reader this control
and nothing else. ``api/live.py:_warm_set`` is the same shape.

Not gated on a linked address
-----------------------------

Unlike the swap and the sweep, which are signed by the holder's key. Watching a
total or a price needs nothing but a reader, so the gate is the tier alone - and
below it the control is a link to subscriptions rather than a disabled button.
A dead control teaches a reader the feature is broken; a link teaches them it
costs something.

The allowance
=============

``tiers.py``. Trial 0, Intro 0, Asastatser 5, Professional 25, Cluster 50, set
by the account holder 2026-09-21.

.. warning::

   **These are not the liverefresh bands and must never be derived from them.**
   That widget bands how many *addresses* a reader may watch - 1 / 1 / 5 / 20.
   This bands how many *rules* they may keep. ``api/tiers.py`` records that this
   project has already conflated two tier axes twice because they share tier
   names. ``test_alerts_tiers_are_not_the_liverefresh_bands`` exists so that if
   the two ever become equal by accident, the next person to change one is told.

``rules_allowed`` resolves **descending**, so a permission between two named
tiers lands on the band below rather than on zero. Nothing produces such a value
today, which is exactly why it is worth a test: answering "none" for a paying
reader would look like a billing bug rather than a lookup one.

Build order
===========

From ``notifications/DESIGN.md``. Steps 1-3 are website-only and can land before
any engine work - a rule that is stored and never fires is testable and
harmless.

1. **The rule store and the tier caps.** Done.
2. **The widget and the control.** Done.
3. **The configuration modal**: subject, direction, threshold, window. Done.
4. **Web push delivery**: VAPID keys, the service worker, the subscription
   model, ``push.notify``. Done.
5. **``lvr``, the rule population.** Done - ``population.py``, and **not**
   heartbeat-scored, unlike the three sets beside it.
6. **The per-bundle evaluator and the trigger it answers.** Done, both sides:
   ``evaluate.py`` and ``AlertsRepricedView`` here, and the engine's
   ``utils/alerts.py`` with the ``lvr`` read in its live pass. ``total_value``
   and ``asa_total`` work end to end once both ``.env`` files carry
   ``ALERTS_WEBHOOK_SECRET`` - see ``post-deploy/RUN-alerts-by-hand.md``.
7. **The per-asset evaluator** for ``asa_price``: done - ``engine/core/tasks.py``
   every five minutes over ``lvra``, and ``evaluate_prices`` here.
8. **``total_percent``**, which the price task did *not* unblock - it needed a
   history rather than a fresher reading. Done: the engine keeps a page's totals
   at ``lvth:{page}`` and ``percent_move`` reads them.

   **The one thing to know before changing it:** the comparison is against the
   newest point *at or before* the window's far edge, and returns None when no
   such point exists. A 24-hour rule reports nothing for its first 24 hours.
   Relaxing that to "the oldest point we have" would make every percentage alert
   subtly wrong in a way no notification reveals.

9. **``asa_price_percent``**, the fifth subject and the one that needed both
   halves. Done: the price task already had the prices, so it writes each one to
   ``lvah:{asset id}`` as it goes - the same bucket-and-trim write the live pass
   does for a page's totals - and ``percent_move`` reads that series through its
   ``prefix`` argument. One function answers both percentage subjects, which is
   deliberate: a second copy would be a second place for the far-edge rule above
   to rot.

   **Two things it required elsewhere.** ``publish_assets`` had to widen from
   ``asa_price`` to ``models.PRICED_SUBJECTS``, or an asset named only by
   percentage rules would never be priced and its series would stay empty
   forever - a rule refusing every reading looks exactly like one that has not
   crossed yet. And ``AlertRule.subject`` had to widen from 16 characters to 32:
   ``asa_price_percent`` is 17. That is migration ``widgets/0003``.

Traps waiting in the later steps
================================

**The service worker must be served from** ``/``, not ``/static/``, or its scope
is limited to the static path. ``core_views.index_file`` already serves
``robots.txt`` from root - copy it rather than inventing an nginx rule.

**iOS Safari supports web push only for home-screen-installed PWAs.** A share of
readers will enable alerts and receive nothing. The enable flow has to detect
and say so; leaving them to discover it is the one real cost of choosing push
over a webhook.

**VAPID keys are a key-management tail**, and belong where the router signer's
key does - not in the repo. Deploys are Ansible-only.

**The thin-asset problem applies to** ``asa_price`` **with a window, and only
then.** An absolute threshold reads a current price, which ``appstransmitter``
keeps fresh every ~2.7 s for every key still inside its TTL in
``CACHE_TRANSMITTER_SET``. A percentage over a period needs a series, and the
series is event-driven: gaps of p50 5 minutes, p90 68 minutes, max 17.5 days.
A short window on an illiquid asset may contain one point or none.

Tests
=====

.. code-block:: bash

   source /home/ipaleka/dev/venvs/frontend/bin/activate
   python -m pytest website/widgets -q

Run the widget suite as its own invocation, never combined with the host suite -
``widgets/inhouse/historic/tests/conftest.py`` installs fake modules at import
time so the suite can run standalone, and anything importing those modules after
collection gets the stub.

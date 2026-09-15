Real-time refresh widget
========================

Operational runbook for the ``liverefresh`` widget. Build and contract rules are in
:doc:`/development` and :doc:`/widget_contract`.

The widget holds almost no logic. The engine's live pass re-prices a watched address
page on every block and publishes the result to this deployment's own Redis; this reads
that and swaps the figures that moved into the page. **Serving the poll is also the
subscription** — there is nothing to unsubscribe, because a reader who closes the tab
simply stops polling and the page ages out of the engine's work.

Configuration
-------------

Frontend constants, in ``utils/constants/core.py``:

- ``LIVEREFRESH_POLL_SECONDS`` — seconds between polls, default ``3``. About one Algorand
  block (measured p50 2.721 s). Shorter asks the same question twice; longer is a page
  visibly behind the explorer.
- ``LIVEREFRESH_HIDDEN_GRACE_SECONDS`` — how long polling continues after the tab is
  hidden, default ``300``. Not zero, so switching tabs for a moment costs no catch-up
  render; not unlimited, because every polling tab holds a subscription the engine
  re-prices every block.

Engine settings (the other service — it must be running the pass for any of this to do
anything):

- ``TRANSMITTER_LIVE_ADDRESSES`` — pages re-priced unconditionally, for measurement.
  Hand-edited, and **Python concatenates adjacent string literals**: a missing comma
  silently fuses two addresses into one that can never resolve. Check
  ``len(settings.TRANSMITTER_LIVE_ADDRESSES)``, never the line count.
- ``TRANSMITTER_LIVE_MAX_PAGES`` — most pages one block will re-price, pinned and
  subscribed together, default ``200``. Over it the pass keeps the pinned pages and the
  *freshest* readers and sheds the stalest; a shed reader sees what a non-subscriber sees.
  Zero disables the limit.
- ``TRANSMITTER_LIVE_HOLDINGS_CAP`` — pages one worker retains, default ``64``. Retention,
  not admission. Keep it at or above ``TRANSMITTER_LIVE_MAX_PAGES`` or the surplus becomes
  re-reads (about 4x a re-price, and far worse on a heavy page).
- ``TRANSMITTER_LIVE_REREAD_BLOCKS`` — the backstop, default ``60`` blocks (~2.7 min).
  **It means blocks since 2026-09-15**; it counted a worker's own re-prices before, which
  at 14 stripes made the real period 840 blocks. It has a ceiling as well as a floor: NFT
  floor prices come from cron every 15 minutes, so past ~330 blocks an NFT-heavy page
  shows floors older than the data behind them.
- ``TRANSMITTER_LIVE_TOUCHED_BLOCKS`` — most blocks one cycle reads looking for accounts
  that transacted, default ``16``. Only reached when the pass is catching up.

Redis keys, on the liveserver's own instance unless noted:

- ``lvx`` — sorted set of watched pages, scored by the unix time this widget last served
  a poll for them. The engine drops a page 90 s after its last beat.
- ``lvp:<page>`` — the published block, msgpack, 120 s TTL.
- ``lvs`` — page → valued holdings, which is what admission control charges.
- ``lvh`` — page → the holdings fingerprint, ``<counter>:<digest of the asset ids>``. The
  widget compares it against ``data-holdings`` on the page and answers a difference with
  ``HX-Refresh``; the address page's own cache entry is keyed on it too, so the reload
  cannot be served the markup that prompted it.
- ``lvf:<user id>`` — one free reader's spend today: ``day``, ``used``, ``seen``. Expires
  after 48 h.
- ``lvd`` — **on the shared instance**, not this one: addresses a collector has corrected
  the cached data behind. The engine drains it each block and re-reads those pages. It is
  on 6379 because the collectors run in the other transmitter.

**No engine scopes.** The manifest declares none: nothing is called on the reader's
behalf. A deployment that cannot reach the engine's HTTP API can still host this, as long
as its own engine runs the pass.

Who may use it
--------------

**Two separate limits, and they are easy to confuse.** How many addresses a reader may
watch at once is one question; how long they may watch per day is another. A tier answers
both, and never with the same number.

====================== ============================ ==========================
Reader                 Addresses watched at once    Watching time per day
====================== ============================ ==========================
anonymous              0                            none
authenticated, no tier 1                            15 minutes
Intro                  1                            30 minutes
Asastatser             1                            no limit
Professional           5                            no limit
Cluster                20                           no limit
====================== ============================ ==========================

So **Asastatser is one address, for as long as they like** — "unlimited" in this widget
never means addresses. Anonymous readers are excluded by the access mixin's
``is_authenticated`` check before any band is consulted, not by a band.

**Addresses, not tabs** — one bundle of five in a single tab, five tabs holding one
address each, or any combination. The address bands live in ``widget.toml``; the daily
minutes live in ``allowance.py``, because a manifest band cannot express a duration.

The two are counted differently, which follows from that. The address limit is applied per
page request, against the number of addresses that page resolves to. The time limit is per
reader per day across every tab they have open: each poll charges the gap since that
reader's *previous* poll, capped at two intervals, so five tabs spend one second per
second rather than five — their polls interleave and each charges a fifth of the gap. A
reader who shuts the laptop for an hour is charged the cap, not the hour.

Both halves are required for the poll to render: the reader must clear the address band
*and* have ticked **Real-time refresh** in profile settings. Every authenticated reader
clears the band for one address, so the opt-in is open to all of them — it has to be, or
the daily allowance would be unreachable.

Running out is not silent. The view answers ``HX-Trigger: liverefresh:spent``, and
``liverefresh.js`` stops polling, reveals ``#id-liverefresh-spent`` and removes the marker
— which hands the page back to ``address.js``'s 60-second reload, since that timer stands
down only while the marker is present. A reader left with neither the live updates nor the
reload would be worse off than one who never had the feature.

Operations
----------

Checking it is working
^^^^^^^^^^^^^^^^^^^^^^

Run the inspector on the liveserver and rsync the file::

    python live/tools/inspect_liveserver.py > /var/www/asastats.com/logs/liveserver.txt

Two columns answer most questions:

- ``usdc`` **must move every block.** It is the ALGO price, re-read on each re-price. If
  it is identical across two dumps minutes apart, the engine's re-read is not landing and
  every dollar figure on every watched page is stale.
- ``changed N`` counts the holdings whose value moved **since that worker last held the
  page** — which is not "since last block". ``_live_holdings`` is worker-local and
  deliberately unpinned, so the gap varies and this number with it: a 120-asset page swung
  between 12 and 76 over five consecutive samples. A worker that is not holding the page
  re-reads it and publishes the whole set, logging ``live read`` instead of
  ``live repriced``.

  A high number is therefore not a fault. What is one is the count sitting at the page's
  *full* holding count on every block — nothing is being retained, so check
  ``TRANSMITTER_LIVE_HOLDINGS_CAP`` against the number of watched pages.

``lvx`` in the same dump lists who is being watched. An empty ``lvx`` with readers who
believe they opted in points at the gate, not at the pass.

When nothing updates for one reader
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In the order worth checking:

1. **Their allowance.** Below Asastatser it is 15 or 30 minutes a day, and it runs out
   quietly from the server's side: the page stops polling, shows
   ``#id-liverefresh-spent`` and falls back to the 60-second reload. Check
   ``lvf:<user id>`` — fields ``day``, ``used``, ``seen`` — before anything else. This is
   the most common answer now.
2. **Layout.** Both layouts are served since 2026-09-15; the widget picks a fragment set
   from ``layout_for_user``. A reader seeing nothing on *either* layout is not a layout
   problem, but a reader on one layout seeing the other's markup swapped in would be —
   check ``fragments.html``'s branch and the ``layout`` in its context.
3. **The opt-in**, then the band. Both are required and neither implies the other; every
   authenticated reader clears the band for one address.
4. **The marker.** ``#id-liverefresh`` arrives in the page's non-cached partial. If the
   page is served from cache without it, that is the address page's cache, not this
   widget — per-reader state must never be rendered into it.
5. **The pass.** No ``lvp:`` key for that bundle means the engine has not published it;
   the widget answers ``204`` and leaves the page alone.

Capacity
^^^^^^^^

``TRANSMITTER_LIVE_MAX_PAGES`` bounds it. Past the limit the pass keeps the pinned pages
and the freshest readers and drops the rest, logging once per change::

    live pass at capacity: 260 pages wanted, 200 admitted, 60 readers shed
    (TRANSMITTER_LIVE_MAX_PAGES=200, 50 pinned)

**That warning is the signal to act**, not an error. It means readers are being turned
away, so either raise the limit against measurement or cut the pinned list.

The limit exists because the failure without it is not gradual: past the point where the
pass no longer fits its block the whole wave starts missing rounds, and the feature goes
quiet for *everybody* rather than for the readers past the limit. A shed reader sees what
a reader who never subscribed sees — a page that does not update.

Sizing, measured (2026-09-15): about 9 ms to re-price a page in production and 60–160 ms
to read one; a 7,002-NFT bundle is 0.35 s and 1.7 s respectively. Fifty pages measured
1.557 s of serial work per cycle, and the cycle did not move — the pass is a few percent
of it. Raise the limit against ``live/tools/pass_stats.py`` rather than against a guess,
and raise ``TRANSMITTER_LIVE_HOLDINGS_CAP`` with it.

Turning it off
^^^^^^^^^^^^^^

There is no switch, and it needs none. Stopping the engine's pass expires the ``lvp:``
keys after 120 s, after which the widget answers ``204`` for every poll and every page
stays exactly as it was rendered. Removing the widget stops the marker rendering and
readers fall back to the 60-second reload.

Tests
-----

Three suites, run separately::

    cd widgets/inhouse/liverefresh && npx jest        # the poll, 100% enforced
    python -m pytest widgets/inhouse/liverefresh      # view, fragments, bands
    python -m pytest functional_tests/test_liverefresh_page.py

The browser suite is the one that matters most here and the one that has found the real
bugs: the poll bound to an event the dynamic layout's control never fires, and an
unquoted attribute that swallowed the next one. A feature that only exists in a browser
cannot be signed off from unit tests.

Links
-----

- Design and measurements: ``~/claude/live/ANALYSIS.md``
- Deployment: ``~/claude/live/DEPLOY.md``
- Extending it to the legacy layout: ``~/claude/live/CLASSIC-LAYOUT.md``

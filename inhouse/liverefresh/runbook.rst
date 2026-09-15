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

Redis keys, on the liveserver's own instance:

- ``lvx`` — sorted set of watched pages, scored by the unix time this widget last served
  a poll for them. The engine drops a page 90 s after its last beat.
- ``lvp:<bundle>`` — the published block, msgpack, 120 s TTL.

**No engine scopes.** The manifest declares none: nothing is called on the reader's
behalf. A deployment that cannot reach the engine's HTTP API can still host this, as long
as its own engine runs the pass.

Who may use it
--------------

============= ==========================================================
Tier          Addresses watched live
============= ==========================================================
Asastatser    1
Professional  5
Cluster       20
============= ==========================================================

**Addresses, not tabs** — one bundle of five in a single tab, five tabs holding one
address each, or any combination. The bands live in ``widget.toml``.

Both halves are required for the poll to render: the tier must allow it *and* the reader
must have ticked **Real-time refresh** in profile settings. A reader who never opted in,
or whose tier has lapsed, keeps the free 60-second page reload instead.

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

1. **Layout.** The out-of-band swaps address ids that only the dynamic layout renders.
   ``liverefresh.js`` checks for a swap target and deliberately does not poll without
   one, so a reader on the legacy layout sees nothing and costs nothing. This is the most
   common answer.
2. **The opt-in**, then the tier. Both are required and neither implies the other.
3. **The marker.** ``#id-liverefresh`` arrives in the page's non-cached partial. If the
   page is served from cache without it, that is the address page's cache, not this
   widget — per-reader state must never be rendered into it.
4. **The pass.** No ``lvp:`` key for that bundle means the engine has not published it;
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

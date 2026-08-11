HOGSWAP router widget
=====================

Operational runbook for the ``hogswap`` swap widget. Build and contract rules are in
:doc:`/development` and :doc:`/widget_contract`.

Configuration
-------------

Host settings the widget reads (frontend configuration). **Both are optional and
both default to empty**, which is a working free-tier deployment:

- ``HOGSWAP_BASE_URL`` — override the API host. Empty means the SDK's own
  default, ``https://hogswap-v1.liquihog.dev``, which is what production uses.
  It exists so a staging deployment can be pointed elsewhere without a code
  change. **A value set here must also be added to the manifest's ``hosts``**,
  or the browser will be blocked from reaching it.
- ``HOGSWAP_API_KEY`` — HOGSWAP's ``hsk_`` key for its paid tier. A throughput
  key rather than a fund-access secret, so it is necessarily client-visible.
  The free tier needs none.

This widget earns nothing
-------------------------

There is no referrer, partner or integrator-fee parameter anywhere in the
HOGSWAP SDK, so unlike Folks (``feeBps`` + ``referrer``) and Haystack
(``referrerAddress``) there is nowhere to name ourselves. The manifest's
``revenue_account`` is empty in fact and not merely by convention.

What the user pays is HOGSWAP's own 5 basis points, waived in proportion to the
HOG their wallet holds and free at 100 — a property of the caller's wallet
rather than of the trade. The widget passes ``sender`` on every quote so that
discount is priced into what the user is shown.

Operations
----------

Quote expiry
^^^^^^^^^^^^

A HOGSWAP quote id expires **30 seconds** after issue and funds at most five
builds. The shared controller quotes as the user types and builds the group only
when they confirm, which routinely exceeds that, so ``buildSwapGroup`` re-quotes
once on ``QuoteExpiredError`` rather than failing the swap.

The consequence worth knowing: a user who leaves a confirmation dialog open may
be signing a group built from a *newer* quote than the screen shows. They cannot
be filled below the tolerance they chose — the replacement carries its own
``min_out_at_slippage``, which the HOGSWAP contract enforces — but the price may
differ from the one displayed. If that ever needs to change, the fix is a
re-confirmation step in the controller rather than anything in this adapter.

Rate limits
^^^^^^^^^^^

30 quote requests per 10 seconds, 4 concurrent per IP. These are *per browser*,
not per deployment, because every call is made from the user's own machine — so
a busy site does not exhaust a shared budget the way a server-side integration
would.

The opt-in is ours to add
^^^^^^^^^^^^^^^^^^^^^^^^^

HOGSWAP's ``/execute`` does **not** bundle the user's opt-in into the output
asset, and its group is unexecutable without one. Verified against mainnet on
2026-08-11 by simulating a 5 ALGO → USDt build for an address not holding USDt:
the group they returned fails with ``must optin, asset 312769 missing from
…``, at their own inner transaction.

What makes the widget work is the shared controller's generic path — it
compares the target asset against live holdings and has the wallet bridge
prepend the opt-in into the same atomic group. The same simulation with that
opt-in prepended and the group re-assigned passes, so their router reads its
group relatively and tolerates the extra leading transaction. Both halves of
that were assumptions until they were simulated; neither is exercised by
swapping into an asset the user already holds, which is why a first-ever swap
into a new asset is the case to test after any change here.

One forward-looking caveat: SDK 1.4.0 added ``MissingOptInError`` (HTTP 422
``missing_opt_in``, ids on ``.assets``) and its source says "opt in, then
request a fresh quote". The API did not raise it in the run above — it built
the group happily. If HOGSWAP switches that on server-side, ``/execute`` will
refuse *before* returning anything to prepend to, and this widget will need a
pre-flight opt-in via the bridge's ``optIn()`` instead. Worth re-testing when
the SDK next moves.

Troubleshooting
^^^^^^^^^^^^^^^

- **Every quote fails with a network error** — check the manifest ``hosts``
  entry still matches the SDK's default base URL. The widget declares one host
  and nothing else; a vendor change of hostname breaks quoting entirely.
- **Quotes work, signing fails** — HOGSWAP returns an *unsigned* group, so the
  shared controller's ``signAndSend`` path applies and only the wallet bridge's
  plain ``signer`` is used. Unlike Haystack there is no router-specific signer;
  if one appears to be needed, something else is wrong.
- **A pair quotes on their site and not here** — the widget requests plain
  forward swaps only. HOGSWAP's LP, multi-input and basket modes are not wired
  up, and its exact-out mode rejects some parameters the forward mode accepts.

Links
-----

- HOGSWAP: https://hogswap-v1.liquihog.dev
- SDK: https://github.com/LiquiHog/hogswap-js-sdk (``hogswap-js-sdk`` on npm)

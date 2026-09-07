ASA Stats router widget
=======================

Operational runbook for the ``asastats`` swap widget. Build and contract rules are in
:doc:`/development` and :doc:`/widget_contract`.

This is the only router widget whose router is ours. Folks and Haystack are vendors
reached from the browser by their own SDKs; this one quotes in the ASA Stats engine and
the browser talks only to us.

State
-----

**The two engine endpoints exist and this widget is published.** ``core/urls.py``
routes both, implemented as ``InternalRouterQuoteView`` and
``InternalRouterGroupView`` with ``required_scope`` set to match:

- ``router:quote`` → ``POST /api/v2/internal/router/quote/``
- ``router:group`` → ``POST /api/v2/internal/router/group/``

Both must also appear in the deployment token's ``scopes``; ASA Stats grants those at
the engine and a fork cannot raise its own.

**Quoting and group building both work.** Mainnet has been ``restricted=False``
since 2026-08-30, and the frontend's
``integration_tests/test_asastats_integration.py`` now asserts that a group comes
back rather than a 503 --- the predecessor test pinned the refusal while predicting
its own obsolescence, and that prediction came true.

.. note::

   Until then, ``engine/core/router.py:_deployment()`` raised
   ``RouterUnavailable`` for a restricted deployment and the view turned it into a
   503, so a reader could see a quote and not execute it. Two things are worth
   keeping from that period. A 503 is **still reachable**, for other reasons ---
   an unavailable quote signer is one --- so it is not by itself evidence that the
   deployment has been restricted again. And the mainnet application id changes
   with each redeployment; ``router/deployments.py`` is the one place that knows
   which one is live, and every setter and verifier reads it from there.

.. warning::

   An earlier version of this section said to *leave the widget unpublished rather
   than published-and-broken, because* ``category = "swap"`` *means the registry
   would otherwise offer it as a selectable router*. **That mitigation never
   worked, and it caused a live bug.**

   ``widgethost.registry`` discovers a widget from the presence of its
   ``widget.toml``, and ``swap_routers()`` returns everything declaring
   ``category = "swap"`` — neither consults ``INHOUSE_WIDGETS``. Leaving the widget
   out of that list therefore stopped its **URLs being mounted** while doing nothing
   at all to stop it **being offered**. Worse, ``swap_routers()`` sorts by id and
   ``asastats`` sorts first, so ``Profile.preferred_router_or_default`` returned it
   as the default for every profile that had never chosen a router — whose entry URL
   then resolved to ``""``, because ``swap_entry_url`` swallows ``NoReverseMatch``
   and returns empty so callers "degrade gracefully".

   Nothing failed loudly and nothing logged. The lesson is that discovery and
   mounting are two mechanisms: a widget is hidden only when its manifest says so,
   never by being left off a list.

The routing code these wrap is the smart router package, whose quoting entry points
are ``router.quote.quote_fixed_input`` and ``router.quote.quote_fixed_output``, and
whose group builder is ``router.legs.legs_for_quote`` followed by
``router.build.assemble``.

Browser-side tests
------------------

``AsastatsAdapter`` lives in ``inhouse/swapcore/static/swap/swap.js`` beside the other
two adapters and is covered by ``describe("AsastatsAdapter")`` in
``inhouse/swapcore/tests/javascript/index.test.js``. Run it with ``npm test`` from
``inhouse/swapcore``; ``swap.js`` is at 100% statements, branches, functions and lines.

Unlike Folks and Haystack there is no vendor SDK to stub — the adapter posts to our own
endpoints — so the tests stub ``fetch`` instead.

Coverage is not the interesting number, and should not be read as one. The check worth
repeating after a change is that the tests still *bite*: mutate the adapter one way at a
time — ``BigInt`` to ``Number``, drop ``credentials: "same-origin"``, drop the CSRF
header, drop the unconfigured-endpoint guard, stop encoding the address, ignore
``response.ok`` — and confirm the suite fails on each. All nine such mutations were
caught when the tests were written.

One of them is a trap worth knowing about. The large-amount test uses
``58180000000000001`` and not ``58180000000000000``: both exceed
``Number.MAX_SAFE_INTEGER``, but the round one is exactly representable as a double and
round trips through ``Number()`` unharmed, so a test using it passes against the very
regression it exists to catch.

Endpoint contract
-----------------

``router:quote`` takes ``{address, from_asset_id, to_asset_id, amount, mode,
slippage_pct, linked_addresses}`` — ``amount`` a decimal **string** in base units,
``mode`` either ``sell`` or ``buy`` — and returns the quote with its amounts
likewise as strings:
``amount_in``, ``amount_out``, ``minimum_received``, ``maximum_sent``,
``price_impact_pct``, ``route_label``, ``fees_total``, plus whatever the group endpoint
needs to rebuild the same allocation.

Strings because the controller works in ``BigInt`` base units and JSON numbers are
doubles: an ALGO amount above about nine quadrillion microALGO would lose precision
silently, and a router that is occasionally wrong about large trades is worse than one
that refuses them.

The fee discount
^^^^^^^^^^^^^^^^

``linked_addresses`` is how the fee tier is judged, and both endpoints take it:
``quote`` prices with the discount and ``group`` mints the voucher that makes the
chain honour it, so sending it to one and not the other reopens the
quoted-versus-delivered gap ``core.router.honoured_discount`` exists to close.

**The view sets it, never the browser.** ``_RouterEndpoint.post`` overwrites
whatever the page sent with :func:`walletauth.gating.algorand_addresses_for_user`
for the signed-in reader, exactly as it does for ``address``. The engine then
reads each address' ASASTATS *for itself* and bands the sum: the body names
addresses, it never names a discount. The published scale counts every linked
address, which is why this is the whole profile rather than the address being
swapped from, and why an EVM connection contributes its lsig counterpart — the
account that actually holds anything on Algorand.

.. warning::

   **This was broken from the day the widget shipped until 2026-09-07, and the
   discount table was published in the meantime.** Two faults in series, each
   hiding the other. The engine read ``request.linked_addresses``, an attribute
   nothing has ever assigned — the same dead-plumbing shape as the
   ``widget_scope`` bug documented beside it — so every caller earned zero.
   Behind that, ``_holdings_for`` returned ``fetch_holdings``' mapping of asset
   id to a *metadata dict* while ``core.discounts.profile_holding`` sums asset
   id to an *amount*, so the first real call would have raised ``TypeError``
   inside the view's broad ``except`` and refused the quote outright.

   Neither was caught because the tests mocked the seam between them: the
   discount tests patched ``_holdings_for`` and returned the shape the policy
   wanted rather than the shape the engine produced, and a ``MagicMock``
   request answers any attribute you ask it for. The regression tests now run
   the two halves against each other instead.

   The Dust Sweep's full waiver was never affected: it comes from
   ``core.sweep.sweep_discount``, which is keyed on the trade rather than the
   caller and touches none of this.

``router:group`` takes ``{address, quote}`` and returns ``{transactions: [...], quote:
{...}}`` — base64, grouped by ``router.build.assemble``, unsigned, alongside the quote
actually built from, which may be marginally better than the one sent.

Two rules the engine side must hold to
--------------------------------------

**The group must honour the floor the user was shown.** Send the quote back rather than
the parameters, and the engine re-derives the allocation against current reserves and
then checks the result still clears that floor — ``409 Conflict`` if it does not, and
the user is asked to quote again.

Re-deriving rather than replaying the quoted allocation is deliberate. Replaying it
means signing a group built against reserves that have since moved; re-deriving and
re-checking guarantees the user gets at least what they were promised or nothing at
all. It also keeps the endpoint stateless, so it does not matter which worker takes the
second request.

**No Tinyman v1 leg may reach this path.** v1 pays out with a top-level transaction sent
by the pool's own logic signature, so a group containing one is not all-user-signed and
cannot be handed whole to the wallet by ``buildSwapGroup``. ``router.build.assemble``
reports which positions need a logic signature; if that map is non-empty the endpoint
must refuse rather than return a group the wallet will reject. Supporting v1 here means
moving this adapter to the ``executeSwap`` shape Haystack uses, which is a larger
change than it looks.

Configuration
-------------

None. There is deliberately no network, referrer, API key or fee setting: the browser
never contacts a router, so no quote parameter lives anywhere a user could edit it. The
platform fee is set on the deployed router application by its admin, not by this widget.

Operations
----------

Fees
^^^^

The router application skims its fee in ALGO from the leg that is already ALGO and
accrues it on-chain, converting to ASASTATS in batches. Nothing here configures that,
and the widget's ``fees_total`` is **not** it — that field is the group's network
transaction cost in microALGO, matching what Folks reports, and is what the panel
renders as "X ALGO fee". The platform fee shows up instead as a slightly smaller
``amount_out``.

Output-asset opt-in
^^^^^^^^^^^^^^^^^^^

Handled the Folks way: the controller re-reads holdings on Swap and runs
``window.asastatsSwap.optIn`` as a separate pre-flight transaction when the target is
not held. The router application opens and closes its *own* holdings inside the group it
builds, which is unrelated — that is its minimum balance, lent for one route and
returned.

Group size
^^^^^^^^^^

A split allocates to several venues and each contract-executed route costs three
transactions, so five routed legs is the ceiling against Algorand's sixteen. The
allocator's ``budget`` is what keeps a quote under it; if quotes start failing to build,
that is the first thing to check.

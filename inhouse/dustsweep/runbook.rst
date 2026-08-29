==========
Dust Sweep
==========

A tool for emptying an account of the asset holdings it no longer wants, and
recovering the ALGO each one locks.

State
=====

.. warning::

   **The close-out half works; the conversion half is blocked on a redeploy.**

   Closing holdings needs no router at all - those groups contain no
   application call - so that path is complete and usable today.

   Conversions route through the ASA Stats router, and the mainnet deployment
   is compiled with ``RESTRICT_TO_ADMIN``. ``engine/core/router.py:_deployment``
   raises ``RouterUnavailable`` for every caller, so no conversion group can be
   built until an unrestricted application is deployed.

   A plan still returns **200**, still offers the close-outs, and names the
   outage in ``conversions_unavailable`` so a caller can tell a swept account
   from a router that cannot build. That is not free: ``plan`` catches the
   exception rather than letting it out. It did let it out until 2026-08-25,
   which turned a restricted router into a 503 for the whole sweep - an account
   with sixteen empty holdings and one convertible one was refused instead of
   being offered its 1.6 ALGO. Found by calling the endpoint for real, after
   this page had already claimed it could not happen.

   Separately, the deployment credential must be granted ``router:sweep``
   before the endpoint answers at all - see `Granting the scope`_. Until then
   the engine answers **403**, and the widget passes that through intact.

What it actually recovers
=========================

**Mostly not the tokens.** An ASA holding locks 0.1 ALGO of minimum balance and
returns it when the holding is closed; one close-out costs 1,000 microALGO. So a
close pays for itself about a hundred times over on a token worth nothing at
all, and on one real account 303 of 314 holdings were already empty - 30.3 ALGO
recoverable without quoting anything.

This is worth saying plainly in the interface, and the page does. A reader who
believes they are selling dust will judge the outcome by the tokens and conclude
it did nothing.

What it does with a holding
===========================

Six dispositions, decided in :mod:`router.sweep`:

============= ==================================================================
``close``     already empty; close it to **self** and take the 0.1 ALGO
``forfeit``   worth less than the minimum balance it locks; close it to the
              asset's **creator** and take the 0.1 ALGO
``convert``   worth converting to ASASTATS first, then closing
``keep``      above the sweep's ceiling, so not dust. Also ALGO, the destination
              asset, and anything frozen
``unpriced``  nothing could value it, so the sweep refuses to guess
``committed`` not free to sweep at all - an NFT, or a token the account holds
              because of a position in some dApp. Shown as **In use**, with the
              disqualifying program named in the reason
============= ==================================================================

What is free to sweep, and what only looks like it
--------------------------------------------------

``account_info`` returns one flat asset list, in which a farm receipt, an LP
token and a forgotten airdrop are indistinguishable. A sweep built on that list
converts and closes tokens that are somebody's **position** rather than their
dust, and the position breaks. This was the first real defect the widget hit.

What can tell them apart is the account evaluation the address page is already
built from. A holding is free to sweep when it is:

* listed in ``asaitems`` **with no program but** ``Balance`` - the engine valued
  it as this address's own wallet holding, **or**
* listed in ``notevals`` under the same program rule - recognised but unvalued,
  still the address's own (it will classify ``unpriced``, so nothing is given
  away on this alone), **or**
* **empty**, *and* carrying no position anywhere. Nothing is left in it to
  belong to a position, and closing it moves no tokens at all;

and it is **not** in ``nftcollections``. That last rule is unconditional and
beats all three positives: an NFT worth nothing today is not dust, and
forfeiting one to its creator destroys something that cannot be re-minted.

Any program but ``Balance`` disqualifies the asset
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The evaluation itemises each holding by program - ``Balance`` for what sits
plainly in the wallet, and ``Staked``, ``Locked``, ``Deposited``,
``Collateral``, ``Supplied``, ``Borrowed``, ``Added`` and the rest for what does
not. **Any of the latter disqualifies the whole asset**, including its
``Balance`` half.

This is a rule about intent, not mechanics. The wallet portion of a staked asset
really is spendable - checked against ``account_info``, ``Balance`` matched the
chain on 245 of 245 holdings - and sweeping it would roughly double what a sweep
finds. But somebody who has staked, lent or collateralised a token has said they
want it, and a sweep is for the ones they do not. It also has real bite: 38 of
the 76 asaitems in the captured sample payload carry more than one program.

It runs **before** the empty rule, which is not a technicality. An account whose
tokens are all staked holds the asset at zero, and that opt-in is the slot the
protocol will pay back into - an ASA cannot be sent to an account that is not
opted in, so closing it would make the eventual withdrawal fail.

A listing with *no* programs at all (the captured payload's one noteval) is read
as "no position recorded" and stays free: the chain supplies the amount, so an
absent ``Balance`` entry says nothing a sweep needs. A malformed program entry
likewise does not disqualify - failing closed there would let a serializer
change silently empty every sweep, and the case where the evaluation cannot be
read at all is handled separately and reported.

Anything else with a balance is, by elimination, held because of something the
account is doing elsewhere. Note this is a rule about *availability*, not value:
raising the threshold cannot reach a ``committed`` holding, and neither can
``opted_in`` - promotion is written against ``unpriced``, which is what makes
the refusal structural rather than a second check somebody could forget.

The evaluation is read for **one address**, keyed on the address itself - never
the bundle it is being viewed inside. A bundle's evaluation answers a different
question ("does *somebody* on this page hold this token") and answers it the
wrong way round: an LP receipt held by another address in the bundle would look
free to sweep out of this one.

When the evaluation cannot be read at all, ``plan`` reports
``evaluation_unavailable``, leaves every holding with a balance alone, and still
offers the empty ones - which is most of what a sweep recovers anyway. The
widget says so rather than letting the reader conclude their account is empty.

Why the creator
---------------

Closing a holding that still has a balance needs somewhere for the balance to
go, and ``asset_close_to`` requires the receiver to be opted in. Verified
against mainnet by simulation:

=========================== ==========================================
target                      result
=========================== ==========================================
the sender itself           REFUSED - ``asset ... not zero``
**the asset's creator**     **OK**
a stranger                  REFUSED - ``receiver error: must opt in``
the reserve address         OK, but only because that asset's reserve
                            happened to be opted in - do not rely on it
=========================== ==========================================

The creator is also the only target that is *structurally* guaranteed: a creator
cannot close out of their own asset while it exists, so their holding is always
there to receive.

Why ``unpriced`` is not a cheap ``forfeit``
-------------------------------------------

Everything else in a sweep fails safe. The forfeit does not: a missing price
reads as a value of zero, zero is below every threshold, and the holding is then
given away. So an unvalued holding is **never** forfeited by default. It is
reported, and a caller may opt it in explicitly through ``opted_in``.

``PRICE_DISAGREEMENT`` guards the opposite direction and does not help here - it
catches a quote that is implausibly *good*, such as OPUL quoting at 1272% of its
priced value.

One group at a time
===================

The endpoint answers with the **next** group to sign, not a plan of everything.
The controller signs it, refetches, and asks again.

* The forfeit has no on-chain floor, so a pre-planned sweep gives tokens away at
  a valuation minutes stale. Deciding immediately before each prompt collapses
  that window to seconds.
* The ordering dependency disappears instead of being managed: a converted
  holding is not closeable until its conversion confirms, and "what is closeable
  now" is just current chain state.
* Quoting is the expensive part - about fifteen seconds per candidate on the
  development machine - so quoting only the candidate that is actually next is
  what makes the endpoint answer at all.
* It needs no new wallet capability. The bridge signs exactly one group per
  call; ``signAndSend`` re-assigns group ids across whatever it is handed, so
  passing it several groups would collapse them into one oversized group.

The rule that makes it cheap
----------------------------

Emit a close-out group only when it is **full at sixteen**, or when nothing
pending could produce another close. Every pending conversion is a future close,
so closing early spends a prompt on a group with slots going spare.

Worked on the settled example - 30 assets, 10 empty, 15 forfeited, 5 converted:
prompt 1 closes 10 empties and 6 forfeits, full at sixteen, banking 1.6 ALGO
immediately; prompts 2-6 convert; prompt 7 closes the remaining 9 forfeits and
the 5 holdings the conversions emptied. **Seven prompts**, against 19-22 when
each disposition is planned and executed in its own pass.

Why sixteen, and why no application can beat it
------------------------------------------------

``MaxTxGroupSize`` is a hard protocol constant. **No application can close
another account's holdings**: an inner transaction's sender must be the
application's own account or one rekeyed to it, so an application-based bulk
close would require the user to rekey their account to it - handing it total
control, and exactly the transaction the router's ``_assert_group_is_clean``
exists to refuse to be bait for. There is no delegation primitive and no
multi-asset close opcode.

D13-style tools (Wen Tools, AlgoWorld) do not use an application either. Their
advantage is handing the wallet several groups in one ``signTransactions`` call -
the lever is the wallet API, not the contract.

What the browser checks
=======================

A close-out group is up to sixteen transactions approved with one click, and
``asset_close_to`` moves an entire balance. Nobody reads the sixteenth line.

So ``dustsweep.js`` decodes the group and checks it **against the plan that
described it** before it reaches the wallet - ``closeOutProblems``. Not because
the engine is expected to lie, but because "the engine said so" is the only other
assurance on offer, and a control consisting of trusting the thing it checks is
not a control.

* ``axfer`` only, **never** ``pay`` - a payment's ``close`` field drains the
  entire ALGO balance
* zero amount - the close moves the balance by itself
* sender and receiver are both the holder
* no ``rekey``
* the close target is the one the plan named **for that asset id** - self for an
  empty holding, the creator for a forfeit

The last rule is what makes the check bind rather than restate the response: a
group closing a *different* asset, or the right asset to a different address,
fails even though it is a perfectly well-formed close-out.

There is no msgpack decoder on the page and algosdk is a large dependency for a
small job, so ``decodeMsgpack`` reads the subset a transaction uses. Addresses
are compared as raw bytes, which needs base32 only - encoding one back to text
would need SHA-512/256, which WebCrypto does not offer.

The wire format is not the bridge's format
------------------------------------------

The plan is JSON, so its transactions are base64 and its keys snake_case. The
bridge takes neither::

    signAndSend(group: Uint8Array[], opts)
    signAndSendPartial({transactions, signedTransactions, quoteSignerIndex})

``signAction`` converts, and is the only place that does. Handing the strings
through instead produced, from a reader pressing the first close-out button::

    RangeError: Extra 339 of 340 byte(s) found at buffer[1]

which names neither base64 nor this widget: ``decodeUnsignedTransaction``
coerces an array-like of characters into one byte each, and a close-out is
exactly 340 base64 characters, so msgpack read a complete object in the first
byte and called the other 339 trailing garbage. **This is not a symptom of a
restricted deployment.** ``RESTRICT_TO_ADMIN`` can only take the *conversion*
half away, and it says so in ``conversions_unavailable``; a close-out group is
built by ``router.sweep.close_out_group`` from suggested parameters alone and
never reaches the router application at all.

The fee waiver
==============

A sweep conversion pays no platform fee. That waiver is granted by
``core.sweep.sweep_discount`` on properties of the **trade** - the output is
ASASTATS, the input is positively valued and at or below the sweep's ceiling -
and never on properties of the caller.

It used to be keyed on ``request.widget_scope == "router:sweep"``. That was dead
(nothing ever assigned ``widget_scope``) and would have been a hole had it
worked: a scope is carried by the deployment's *token*, which the widget sends
with every request it makes, so a token granted the sweep scope would have waived
the entire platform fee on every ordinary swap anyone quoted with it.

Granting the scope
==================

``HasWidgetScope`` refuses any endpoint whose scope the credential does not
carry, so the engine answers 403 until::

    python manage.py create_deployment "<deployment name>" --grant \
        --scope router:sweep

``--list`` shows what a deployment already holds. ``router:sweep`` is
deliberately its own scope rather than a reuse of ``router:quote``: a deployment
that can quote a swap must not thereby be able to plan a sweep for any address
it names.

Endpoints
=========

``POST /widgets/dustsweep/plan?address=<address>``
    Proxies to ``router:sweep``. Body: ``{threshold_algo, opted_in}``. The
    address is taken from the query string and overwrites whatever the body
    claims, because ownership was gated on that one.

``POST /api/v2/internal/router/sweep/`` (engine)
    Body: ``{address, threshold_algo, opted_in}``. Returns ``summary``,
    ``holdings``, ``refused`` and ``next`` - the group to sign, or ``null``.

Testing
=======

The widget suite runs as its own invocation; combining it with ``api/`` errors
during collection::

    DJANGO_SETTINGS_MODULE=config.settings.development \
        python -m pytest widgets -q

The controller's JavaScript has its own jest suite::

    cd widgets/inhouse/dustsweep && npm install && npm test

Its fixtures are real transactions encoded by algosdk rather than assembled by
hand, because the decoder is being tested against Algorand's canonical msgpack.

Folks router widget
===================

Operational runbook for the ``folks`` swap widget. Build and contract rules are in
:doc:`/development` and :doc:`/widget_contract`.

Configuration
-------------

Host settings the widget reads (frontend configuration):

- ``FOLKS_NETWORK`` — target network (default ``mainnet``).
- ``FOLKS_REFERRER_ADDRESS`` — referral payout address. **Leave unset** unless the
  referrer escrow has been prepared (see *Enabling a referrer*); an unset referrer works.

Operations
----------

$FOLKS fee discounts
^^^^^^^^^^^^^^^^^^^^^

Holding ``$FOLKS`` reduces the router fee. Nothing to configure: the SDK applies it
on-chain via ``fetchUserDiscount``, which ``FolksAdapter.getQuote`` already reads. Worth
surfacing to users as a benefit.

Enabling a referrer
^^^^^^^^^^^^^^^^^^^^

Setting ``FOLKS_REFERRER_ADDRESS`` routes the referral fee to a **dedicated escrow Folks
derives per referrer** (in the swap's output asset), so that escrow must be opted into
each output asset before such a swap can succeed. Opt-in is permissionless (the escrow is
a logic-sig account): build it with ``prepareReferrerOptIntoAsset(sender, referrer,
assetId, { ...suggestedParams, flatFee: true })`` — the ``flatFee`` is required, since the
escrow asserts ``Fee == 0``. The escrow needs its base ``0.1 ALGO`` funded once, and each
asset opt-in is preceded by its own ``0.1 ALGO`` payment supplying that asset's minimum
balance. Until this flow is operated for the referrer, ship with the referrer unset.

Claiming referral fees
^^^^^^^^^^^^^^^^^^^^^^^

Referral fees accrue in the per-referrer escrow, per output asset, and are **not**
auto-swept. Move them with a scheduled/admin script built on
``prepareClaimReferrerFees(sender, referrer, assetId, amount, params)``.

Links
-----

- Referral program: https://folksrouter.io/docs/referral-program
- Router / discounts: https://docs.folks.finance/functionalities/folks-router

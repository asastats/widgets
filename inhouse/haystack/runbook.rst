Haystack router widget
======================

Operational runbook for the ``haystack`` swap widget. Build and contract rules are in
:doc:`/development` and :doc:`/widget_contract`.

Configuration
-------------

Host settings the widget reads (frontend configuration):

- ``HAYSTACK_API_KEY`` — public rate-limit key (free tier); necessarily client-visible,
  not a fund-access secret.
- ``HAYSTACK_REFERRER_ADDRESS`` — referral payout address. **Leave unset** until enrolled
  (see below).

Operations
----------

Enabling a referrer
^^^^^^^^^^^^^^^^^^^

Setting ``HAYSTACK_REFERRER_ADDRESS`` makes Haystack's quote endpoint return ``400`` until
the referrer is enrolled with TxnLab. To enrol: visit https://hay.app/holdings, connect
the wallet, open **Referrals**, and register the address. The wiring (setting → marker →
client ``referrerAddress``) is otherwise correct; ship with no referrer until enrolment is
done.

Links
-----

- Haystack holdings / referrals: https://hay.app/holdings

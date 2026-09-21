"""Deciding which rules just fired, from what the engine published.

**The website evaluates, not the engine** - see `notifications/DESIGN.md`. The
rules and their fire state belong to users and live in this database; the engine
only says "page X was re-priced", and everything it computed is already readable
from the Redis both projects share.

**Two evaluators, because there are two shapes of question:**

* `evaluate_page` answers "this page was re-priced". `total_value` and
  `asa_total` read the page's total and its per-asset values, which the pass
  publishes on every block. They are exact.
* `evaluate_prices` answers "these assets have a price now". `asa_price` is not
  per-reader at all - one question per asset however many people watch it - so
  it rides the engine's periodic task rather than any page's re-price.

**One subject is still evaluated by neither**, and deliberately: `total_percent`
needs a *series* of totals over a window, and nothing publishes a history.
Evaluating it against `last_value` would silently redefine the window as "since
we last looked", which is not what the reader chose.

It is **skipped loudly**: `SKIPPED` names it, a rule of that kind is counted,
and the caller logs it. A rule that is stored, looks active and can never fire
is the worst outcome this file could produce.
"""

import logging

from django.utils import timezone

from .models import AlertRule, Subject

logger = logging.getLogger(__name__)

#: Subjects `evaluate_page` does not answer, and why.
#:
#: Kept as data rather than a comment so the count in `evaluate_page`'s return
#: is honest and a caller can say how many rules went unexamined.
#:
#: **The two entries mean different things, and the log should not flatten
#: them.** `asa_price` is answered elsewhere, by `evaluate_prices`; a rule of
#: that kind counted here has not been dropped. `total_percent` is answered
#: nowhere, and a rule of that kind never fires.
SKIPPED = {
    Subject.TOTAL_PERCENT: "needs a series of totals, which nothing publishes",
    Subject.ASA_PRICE: "is per-asset, and is answered by the periodic price task",
}


def reading_for(rule, total, values):
    """Return what `rule` watches, from a published payload, or None.

    :param rule: the rule being evaluated
    :type rule: :class:`widgets.inhouse.alerts.models.AlertRule`
    :param total: the page's total, as the pass published it
    :param values: {asset id: value} for the page
    :type values: dict
    :return: the current reading, or None when it cannot be taken
    """
    if rule.subject == Subject.TOTAL_VALUE:
        return total
    if rule.subject == Subject.ASA_TOTAL:
        # **A missing asset is not a zero.** The pass publishes the holdings it
        # priced; an asset absent from this block's payload was not re-priced,
        # which is different from being worth nothing. Reading it as zero would
        # fire every "falls below" rule the reader has.
        return values.get(rule.asset_id)
    return None


def cooling_down(rule, now):
    """Whether `rule` fired recently enough to stay quiet.

    :param rule: the rule being evaluated
    :param now: the moment being evaluated at
    :return: Boolean
    """
    if rule.last_fired_at is None:
        return False
    return (now - rule.last_fired_at).total_seconds() < rule.cooldown_seconds


def evaluate_page(address, payload, now=None):
    """Return the rules on `address` that just crossed, and record what was seen.

    **Every rule's `last_value` is updated, including the ones that did not
    fire.** A crossing is "past the line now, not past it before", so a reading
    that is skipped leaves the rule comparing against something older than the
    last block - and a value that crossed and came back would be reported the
    next time anything moved.

    **The cooldown is checked before firing, not after.** Checking afterwards
    would still advance `last_fired_at` and push the next legitimate alert
    further away each time the value wobbled.

    :param address: the page the engine re-priced
    :type address: str
    :param payload: what the pass published for it
    :type payload: dict
    :param now: the moment to evaluate at, for tests
    :return: two-tuple of (rules that fired, how many were skipped)
    :rtype: tuple
    """
    now = now or timezone.now()
    total = (payload or {}).get("total")
    values = (payload or {}).get("values") or {}

    fired, skipped = [], 0
    for rule in AlertRule.objects.filter(
        address=address, active=True
    ).select_related("user"):
        if rule.subject in SKIPPED:
            skipped += 1
            continue

        value = reading_for(rule, total, values)
        if value is None:
            continue

        if rule.crossed(value) and not cooling_down(rule, now):
            rule.last_fired_at = now
            fired.append(rule)
        rule.last_value = value
        rule.save(update_fields=["last_value", "last_fired_at", "updated_at"])

    return fired, skipped


def evaluate_prices(prices, now=None):
    """Return the `asa_price` rules that just crossed, and record what was seen.

    The per-asset half, and the only evaluator here that is not per-page. It
    asks "who cares about this asset" once per asset rather than once per rule -
    which is what the `asset_id, active` index on `AlertRule` is for.

    **The prices are the engine's word, not something read back.** Every other
    number this module works from is published to the Redis both projects share;
    an asset's price is not. It lives in the engine's *primary* cache, which the
    website has no client for, so it arrives in the signed body instead. That is
    what the HMAC is protecting - see `views.signature_ok`.

    The crossing, the arming and the cooldown are `evaluate_page`'s, for the same
    reasons; only the reading is fetched differently.

    :param prices: {asset id: price in ALGO}, as the engine computed them
    :type prices: dict
    :param now: the moment to evaluate at, for tests
    :return: the rules that fired
    :rtype: list
    """
    now = now or timezone.now()
    if not prices:
        return []

    fired = []
    for rule in AlertRule.objects.filter(
        subject=Subject.ASA_PRICE, active=True, asset_id__in=list(prices)
    ).select_related("user"):
        value = prices.get(rule.asset_id)
        # **A price the engine could not compute arrives as None, not as zero.**
        # An asset with no pool left prices at nothing, and reading that as a
        # collapse to zero would fire every "falls below" rule naming it at
        # once - which is precisely the asset most likely to have rules on it.
        if value is None:
            continue

        if rule.crossed(value) and not cooling_down(rule, now):
            rule.last_fired_at = now
            fired.append(rule)
        rule.last_value = value
        rule.save(update_fields=["last_value", "last_fired_at", "updated_at"])

    return fired


def payload_for(address, client=None):
    """Return what the pass last published for `address`, or None.

    Reads the engine's Redis directly, exactly as the live-refresh widget's own
    view does - the two projects share the instance, and this is the same key it
    polls for.

    :param address: the page
    :type address: str
    :param client: an open Redis client, or None to make one
    :return: the decoded payload, or None
    """
    import msgpack  # noqa: PLC0415 - only this path needs it

    from utils.clients import redis_instance  # noqa: PLC0415

    try:
        client = client or redis_instance()
        raw = client.get(f"lvp:{address}")
    except Exception as error:  # noqa: BLE001 - a webhook must not 500 on this
        logger.warning("could not read the published payload: %s", error)
        return None
    if not raw:
        return None
    # `strict_map_key=False` because the values map is keyed by asset id as an
    # integer, which is how the fragments address it and how `reading_for`
    # looks it up.
    return msgpack.unpackb(raw, strict_map_key=False)

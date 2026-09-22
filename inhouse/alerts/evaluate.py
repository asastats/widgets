"""Deciding which rules just fired, from what the engine published.

**The website evaluates, not the engine** - see `notifications/DESIGN.md`. The
rules and their fire state belong to users and live in this database; the engine
only says "page X was re-priced", and everything it computed is already readable
from the Redis both projects share.

**Two evaluators, because there are two shapes of question:**

* `evaluate_page` answers "this page was re-priced". `total_value` and
  `asa_total` read the page's total and its per-asset values, which the pass
  publishes on every block. `total_percent` rides the same trigger but reads a
  *second* number - the page's total one window ago - out of the history the
  engine keeps at `lvth:{page}`.
* `evaluate_prices` answers "these assets have a price now". `asa_price` and
  `asa_price_percent` are not per-reader at all - one question per asset however
  many people watch it - so they ride the engine's periodic task rather than any
  page's re-price. The percentage one reads its second number from `lvah:{asset
  id}`, which that same task writes as it prices.

**The rule that makes both percentage subjects honest is in `percent_move`:** it compares
against the newest point *at or before* the window's far edge, and returns None
when the history does not reach that far. A rule with a 24-hour window therefore
fires nothing for its first 24 hours. The alternative - comparing against
whatever the series happens to hold - silently turns "down 5% in 24 hours" into
"down 5% since we started watching", and nothing in the notification would
reveal it.

What `SKIPPED` still names is **skipped loudly**: a rule of that kind is
counted and the caller logs it. A rule that is stored, looks active and can
never fire is the worst outcome this file could produce.
"""

import logging
import time

from django.utils import timezone

from django.db.models import Exists, OuterRef

from .models import (
    CURRENCY_SUBJECTS,
    PRICED_SUBJECTS,
    AlertRule,
    PushSubscription,
    Subject,
)

logger = logging.getLogger(__name__)

#: Subjects `evaluate_page` does not answer, and why.
#:
#: Kept as data rather than a comment so the count in `evaluate_page`'s return
#: is honest and a caller can say how many rules went unexamined.
#:
#: A rule counted here **has not been dropped** - `asa_price` is per-asset and
#: is answered by `evaluate_prices` on the engine's periodic task.
SKIPPED = {
    Subject.ASA_PRICE: "is per-asset, and is answered by the periodic price task",
    Subject.ASA_PRICE_PERCENT: (
        "is per-asset, and is answered by the periodic price task"
    ),
}

#: Where the engine keeps a page's totals over time: `lvth:{page}`.
#:
#: Named as a literal for the same reason `population` names `lvr` as one: the
#: two projects share a Redis rather than a codebase, and the engine's
#: `CACHE_KEY_LIVE_TOTALS_HISTORY` is the other half of this contract.
HISTORY_KEY = "lvth"

#: Where the engine keeps an asset's prices over time: `lvah:{asset_id}`.
#:
#: Written by the periodic price task, which already has the prices - see the
#: engine's `CACHE_KEY_LIVE_ASSET_HISTORY`.
ASSET_HISTORY_KEY = "lvah"


def _with_delivery(queryset):
    """Annotate `queryset` with whether its reader has a browser to notify.

    **A rule with nowhere to go is held, not spent.** Firing it would set
    `last_fired_at` and advance `last_value` past the threshold, so the next
    evaluation would see no crossing - the alert would be gone rather than
    waiting, and the modal promises three times over that rules saved now will
    be there when a browser is turned on.

    Annotated rather than filtered so the held ones can be counted and logged:
    "my alert never fired" is the question this answers.

    :param queryset: rules being evaluated
    :return: the same rules, carrying `deliverable`
    """
    return queryset.annotate(
        deliverable=Exists(PushSubscription.objects.filter(user=OuterRef("user")))
    )


def in_rule_currency(rule, algo_figure, algo_per_usd):
    """Return `algo_figure` in the currency the rule is denominated in.

    **The conversion happens here, on the reading, every time it is taken.**
    It used to happen once on the threshold, when the rule was written: a USD
    threshold was turned into ALGO at that day's rate and the reader's choice
    discarded, so "tell me above $500" became a fixed ALGO figure that fired at
    some other dollar amount once ALGO had moved. Converting the reading keeps
    a rule denominated in dollars denominated in dollars.

    **No rate means no reading.** Refusing is the same rule `percent_move`
    applies to a history that does not reach back far enough: a comparison that
    cannot be made honestly is not made. Answering in ALGO against a threshold
    the reader typed in dollars would be wrong by whatever an ALGO costs.

    :param rule: the rule being evaluated
    :type rule: :class:`widgets.inhouse.alerts.models.AlertRule`
    **Divided, not multiplied, and that is the whole of it.** `algo_per_usd` is
    how much ALGO one USD buys - about 4 when ALGO is $0.25 - which is what the
    engine publishes as `priceusdc` and what the address page labels "ALGO/USD".
    `account_totals` does `totalusdc = total / price_usdc` and `address.js`
    divides to show a dollar figure; this has to agree with both. A name like
    "the ALGO price" is how this widget converted it backwards three times.

    :param algo_figure: the reading, in ALGO
    :param algo_per_usd: how much ALGO one USD buys, or None
    :return: the reading in the rule's own currency, or None
    """
    if algo_figure is None:
        return None
    if rule.subject not in CURRENCY_SUBJECTS or rule.threshold_unit != "usd":
        return algo_figure
    if not algo_per_usd:
        logger.warning(
            "alerts: rule %s is in USD and no ALGO/USD rate was published", rule.pk
        )
        return None
    return float(algo_figure) / float(algo_per_usd)


def reading_for(rule, total, values, client=None, now=None, amounts=None,
                algo_per_usd=None):
    """Return what `rule` watches, from a published payload, or None.

    :param rule: the rule being evaluated
    :type rule: :class:`widgets.inhouse.alerts.models.AlertRule`
    :param total: the page's total, as the pass published it
    :param values: {asset id: value} for the page
    :type values: dict
    :param client: an open Redis client, for the subjects that read a history
    :param now: unix time, for tests
    :param amounts: {asset id: [amount, decimals]} for the page
    :type amounts: dict
    :param algo_per_usd: how much ALGO one USD buys, for a USD rule
    :return: the current reading, or None when it cannot be taken
    """
    if rule.subject == Subject.TOTAL_VALUE:
        return in_rule_currency(rule, total, algo_per_usd)
    if rule.subject == Subject.TOTAL_PERCENT:
        # The one reading that is not in the payload: it needs two totals, and
        # the payload carries one. See `percent_move` for why a short history
        # answers None rather than answering over a shorter period.
        return percent_move(
            rule.address, rule.window_seconds, total, client=client, now=now
        )
    if rule.subject == Subject.ASA_TOTAL:
        # **A missing asset is not a zero.** The pass publishes the holdings it
        # priced; an asset absent from this block's payload was not re-priced,
        # which is different from being worth nothing. Reading it as zero would
        # fire every "falls below" rule the reader has.
        return in_rule_currency(rule, values.get(rule.asset_id), algo_per_usd)
    if rule.subject == Subject.ASA_AMOUNT:
        return holding_amount(amounts, rule.asset_id)
    return None


def holding_amount(amounts, asset_id):
    """Return how much of `asset_id` is held, in whole units, or None.

    **The payload carries base units and the decimals to read them with**, as
    `[amount, decimals]`, because an amount is meaningless without them - a
    value is already in ALGO and an amount is in the asset's own scale. The
    reader's threshold is in whole units, which is what they typed, so the
    conversion happens here rather than being asked of them.

    None for an asset the block did not mention, exactly as a value is. A
    holding that did not change is not a holding of nothing - and for this
    subject that matters more than for any other, because the reader is
    waiting for it to change.

    :param amounts: {asset id: [amount, decimals]} for the page
    :type amounts: dict
    :param asset_id: the asset the rule names
    :type asset_id: int
    :return: float or None
    """
    entry = (amounts or {}).get(asset_id)
    if not entry:
        return None
    try:
        amount, decimals = entry[0], entry[1]
        return float(amount) / (10 ** int(decimals))
    except (TypeError, ValueError, IndexError):
        logger.warning("alerts: unusable amount for asset %s: %r", asset_id, entry)
        return None


def percent_move(page, window_seconds, total, client=None, now=None,
                 prefix=HISTORY_KEY):
    """Return how far `total` has moved over the window, as a percentage.

    **The window is honoured or the question is refused.** This returns None
    unless the history actually reaches back past the window's far edge - it
    compares against the newest point *at or before* `now - window_seconds`, and
    if no such point exists it says so rather than answering with the oldest
    point it happens to have.

    That is the whole reason this subject waited: comparing against the previous
    reading, or against whatever is in the series, quietly turns "down 5% in 24
    hours" into "down 5% since we started watching". The reader would be told
    about a move over a period they did not choose, and there would be nothing
    in the notification to reveal it.

    So a rule with a 24-hour window fires nothing for its first 24 hours, and
    that is correct rather than a gap to paper over.

    :param page: the bundle or address, or an asset id for the asset series
    :type page: str
    :param prefix: which series to read - a page's totals or an asset's prices
    :param window_seconds: the period the reader chose
    :type window_seconds: int
    :param total: the page's total now
    :param client: an open Redis client, or None to make one
    :param now: unix time, for tests
    :return: the signed percentage move, or None when it cannot be taken
    :rtype: float or None
    """
    from utils.clients import redis_instance  # noqa: PLC0415

    if not window_seconds or total is None:
        return None

    edge = (time.time() if now is None else now) - window_seconds
    try:
        client = client or redis_instance()
        # The newest point no younger than the far edge. `zrevrangebyscore` with
        # a limit of one is the whole read - the series may hold two thousand
        # points and exactly one of them answers this.
        members = client.zrevrangebyscore(
            f"{prefix}:{page}", edge, "-inf", start=0, num=1
        )
    except Exception as error:  # noqa: BLE001 - a webhook must not 500 on this
        logger.warning("could not read the totals history: %s", error)
        return None

    if not members:
        return None

    then = _history_total(members[0])
    if then is None:
        return None
    if then == 0:
        # A page that was worth nothing and is worth something has moved by an
        # undefined percentage, not by an infinite one.
        return None
    return (float(total) - then) / then * 100


def _history_total(member):
    """Return the total encoded in a history member, or None.

    Members are `{bucket}:{total}`; the bucket is repeated inside the member so
    that two workers writing the same five minutes leave one point rather than
    two.

    :param member: one member of the sorted set
    :return: float or None
    """
    text = member.decode() if isinstance(member, bytes) else str(member)
    _, _, total = text.partition(":")
    try:
        return float(total)
    except ValueError:
        logger.warning("unusable totals history member: %r", member)
        return None


def _report_muted(muted):
    """Log how many crossings the cooldown swallowed this pass.

    **Silent until now, and it is the one number this decision needs.** The
    cooldown is fifteen minutes for everybody, never measured, and the two
    evaluators run at cadences three orders apart - the live pass every ~2.7 s,
    the price task every five minutes - so one figure is doing two unrelated
    jobs. Whether 900 seconds is right, wrong, or never binds at all is
    answerable from a week of these lines and from nothing else.

    :param muted: crossings suppressed this pass
    :type muted: int
    """
    if muted:
        logger.info("alerts: %s crossing(s) muted by a cooldown", muted)


def cooling_down(rule, now):
    """Whether `rule` fired recently enough to stay quiet.

    **A suppressed crossing is dropped, not deferred**, and that is a decision
    rather than an accident. `last_value` advances whether or not the rule
    fired, so a crossing inside the cooldown is consumed and the reader never
    hears about it - not even late.

    That is the right shape for a crossing model. An alert reports an *event*:
    "fell below 100" was true when it was sent. Holding it back and delivering
    it when the cooldown expired would put "rose above 100" in front of a
    reader thirteen minutes after the fact, where it reads as the current state
    and is not.

    :param rule: the rule being evaluated
    :param now: the moment being evaluated at
    :return: Boolean
    """
    if rule.last_fired_at is None:
        return False
    return (now - rule.last_fired_at).total_seconds() < rule.cooldown_seconds


def evaluate_page(address, payload, now=None, client=None, unix_now=None):
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
    :param client: an open Redis client, for the percentage history
    :param unix_now: unix time, for tests
    :return: two-tuple of (rules that fired, how many were skipped)
    :rtype: tuple
    """
    now = now or timezone.now()
    payload = payload or {}
    total = payload.get("total")
    values = payload.get("values") or {}
    # **Both already in the payload**, which is why two of the five subjects
    # cost nothing: the pass publishes an amount per changed asset with the
    # decimals to read it by, and `priceusdc` for the band across the top.
    amounts = payload.get("amounts") or {}
    # `priceusdc` is ALGO per USD, despite the name. See `in_rule_currency`.
    algo_per_usd = payload.get("priceusdc")

    fired, skipped, held, muted = [], 0, 0, 0
    for rule in _with_delivery(
        AlertRule.objects.filter(address=address, active=True).select_related("user")
    ):
        if rule.subject in SKIPPED:
            skipped += 1
            continue
        if not rule.deliverable:
            # Left exactly as it was, so the crossing is still there when a
            # browser is turned on.
            held += 1
            continue

        value = reading_for(
            rule,
            total,
            values,
            client=client,
            now=unix_now,
            amounts=amounts,
            algo_per_usd=algo_per_usd,
        )
        if value is None:
            continue

        if rule.crossed(value):
            if cooling_down(rule, now):
                muted += 1
                logger.info(
                    "alerts: rule %s (%s) crossed inside its cooldown",
                    rule.pk,
                    rule.subject,
                )
            else:
                rule.last_fired_at = now
                fired.append(rule)
        rule.last_value = value
        rule.save(update_fields=["last_value", "last_fired_at", "updated_at"])

    _report_muted(muted)
    if held:
        logger.info(
            "alerts: %s rule(s) on %s held - their reader has no browser on",
            held,
            address,
        )
    return fired, skipped


def evaluate_prices(prices, now=None, client=None, unix_now=None, depths=None,
                    algo_per_usd=None):
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
    :param client: an open Redis client, for `asa_price_percent`'s history read
    :param unix_now: unix time, for tests
    :param depths: {asset id: pooled depth in ALGO}, attached to what fires
    :type depths: dict
    :param algo_per_usd: how much ALGO one USD buys, for a USD rule
    :return: the rules that fired
    :rtype: list
    """
    now = now or timezone.now()
    depths = depths or {}
    if not prices:
        return []

    fired, held, muted = [], 0, 0
    for rule in _with_delivery(
        AlertRule.objects.filter(
            subject__in=PRICED_SUBJECTS,
            active=True,
            asset_id__in=list(prices),
        ).select_related("user")
    ):
        if not rule.deliverable:
            held += 1
            continue
        value = prices.get(rule.asset_id)
        # **Converted here rather than at creation.** An `asa_price` rule
        # written in dollars stays in dollars; a percentage has no currency and
        # is left alone. See `in_rule_currency`.
        if rule.subject == Subject.ASA_PRICE:
            value = in_rule_currency(rule, value, algo_per_usd)
        if rule.subject == Subject.ASA_PRICE_PERCENT:
            # **The same honesty rule as `total_percent`**, on the series the
            # price task keeps: compared against the newest point at or before
            # the window's far edge, or refused. A 24-hour rule reports nothing
            # for its first 24 hours rather than reporting a shorter move under
            # a longer name.
            value = percent_move(
                rule.asset_id,
                rule.window_seconds,
                value,
                client=client,
                now=unix_now,
                prefix=ASSET_HISTORY_KEY,
            )
        # **A price the engine could not compute arrives as None, not as zero.**
        # An asset with no pool left prices at nothing, and reading that as a
        # collapse to zero would fire every "falls below" rule naming it at
        # once - which is precisely the asset most likely to have rules on it.
        if value is None:
            continue

        if rule.crossed(value) and cooling_down(rule, now):
            muted += 1
            logger.info(
                "alerts: rule %s (%s) crossed inside its cooldown",
                rule.pk,
                rule.subject,
            )
        elif rule.crossed(value):
            rule.last_fired_at = now
            # **Attached at the moment it fires**, because depth is a property
            # of the moment rather than of the rule: an asset that is deep
            # today can be thin next month, so a rule cannot carry it. On the
            # instance rather than in the row - it describes this firing.
            rule.depth_algo = depths.get(rule.asset_id)
            fired.append(rule)
        rule.last_value = value
        rule.save(update_fields=["last_value", "last_fired_at", "updated_at"])

    _report_muted(muted)
    if held:
        logger.info(
            "alerts: %s price rule(s) held - their reader has no browser on", held
        )
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

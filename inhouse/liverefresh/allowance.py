"""How long a reader below the paid tiers may watch a page live.

**A feature nobody has seen is a hard thing to sell.** The tier bands were
all-or-nothing: an authenticated reader below Asastatser got the 60-second page
reload and never saw what the subscription buys - figures moving in place while
scroll position, open rows and filters survive. Ten seconds of watching it makes
the argument that no pricing page can.

    free tier    2 hours, then 15 min a week, on an address they have linked
    Intro        4 hours, then 30 min a week, on any address
    Asastatser+  unlimited

Anonymous readers get nothing, and that is the existing gate rather than a
decision taken here: `BaseUserPassesTestMixin` requires `is_authenticated`. An
allowance needs somewhere to keep a clock, and a cookie is a budget anyone can
reset.

**The free allowance is spent per address, not per account.** An allowance bound
to a user is bound to the cheapest thing in the system - accounts are free and
need no email - so a hundred of them would be a hundred allowances. Bound to the
address, a hundred accounts watching one address all spend the same bucket, and
getting more free time means splitting a portfolio across addresses, which costs
fees and minimum balances and fragments the combined view that was the reason to
watch. The abuse has to destroy the thing it is abusing for.

Intro gets the same refilling bucket on better terms and keyed to the *reader*
rather than the address, because a subscriber is not what that defends against -
and because per-address would be four hours for every address they open, which
is no limit at all.

**The clock lives in Redis, and the truth lives in the database.** A poll
arrives every few seconds per watching reader; a row write per poll would be the
most-written row on the site for a number nobody reads twice. But Redis is
allowed to lose things, and for a daily allowance that costs a reader one day
while for a refilling bucket it would hand every key a fresh grant - the failure
mode of the anti-abuse mechanism must not be the abuse. So Redis carries the
spend between flushes and `LiveAllowanceBucket` carries the balance.

**What is charged is wall-clock, not polls.** Each poll charges the time since
that reader's *previous* poll, capped at `MAX_STEP`. Three consequences, all
wanted: a reader with four tabs open spends one second per second rather than
four, because their polls interleave and each charges the small gap since the
last one; a reader who closes the laptop for an hour is charged the cap rather
than the hour, because they were not watching it; and switching live refresh off
is therefore a pause that needs no separate mechanism - what is not polled is
not charged.
"""

from core.models import LiveAllowanceBucket
from django.utils import timezone
from utils.constants.core import LIVEREFRESH_POLL_SECONDS
from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS

#: Hash holding one bucket's live state. Fields: `balance`, `seen`, `flushed`,
#: `used`. Suffixed with the bucket key - an address, or `u:<pk>`.
SPEND_KEY = "lvf"

#: Seconds a single poll may ever charge.
#:
#: Two poll intervals: enough that an ordinary gap - a slow block, a busy tab -
#: is charged honestly, and short enough that a reader returning after an hour
#: pays for the moment they came back rather than the hour they were away.
MAX_STEP = LIVEREFRESH_POLL_SECONDS * 2

#: How long a bucket's live state is kept in Redis. Two days is far longer than
#: any session, so the row is read once at the start of one rather than
#: repeatedly; losing the entry early costs at most `FLUSH_SECONDS` of spend.
SPEND_TTL = 60 * 60 * 48

#: Seconds of unflushed spend before the durable row is written.
#:
#: The whole point of the Redis layer is that polls do not write rows, and the
#: whole point of the row is that Redis losing an entry must not refund an
#: allowance. Sixty seconds bounds what a lost Redis entry gives back to a
#: minute, at one write a minute per watching reader rather than one per poll -
#: about a twentieth of the writes, for a twentieth of a percent of the bucket.
FLUSH_SECONDS = 60

#: A week, in seconds, which is the unit the refill is quoted in.
WEEK = 7 * 24 * 60 * 60

#: Bucket terms per tier, richest first. `None` is unlimited and never metered.
#:
#: `keyed` is the half that does the anti-abuse work. The free tier's bucket
#: belongs to the *address*, so farming accounts buys nothing; Intro's belongs
#: to the *reader*, because a subscriber is not what that defends against and
#: because per-address would be four hours for every address they open, which is
#: no limit at all.
#:
#: `linked_only` is the other half: a free reader may spend only on addresses
#: they have proved they control, so an abuser cannot simply work through a list
#: of other people's.
TIER_BUCKETS = (
    (SUBSCRIPTION_TIER_PERMISSIONS["Asastatser"], None),
    (
        SUBSCRIPTION_TIER_PERMISSIONS["Intro"],
        {
            "capacity": 4 * 60 * 60,
            "per_week": 30 * 60,
            "keyed": "reader",
            "linked_only": False,
        },
    ),
    (
        0,
        {
            "capacity": 2 * 60 * 60,
            "per_week": 15 * 60,
            "keyed": "address",
            "linked_only": True,
        },
    ),
)


def terms(permission):
    """Return the bucket terms for `permission`, or None when unlimited.

    :param permission: the reader's permission integer
    :type permission: int
    :return: dict or None
    """
    for required, band in TIER_BUCKETS:
        if permission >= required:
            return band
    return None


def bucket_key(permission, address, user_id):
    """Return the bucket key this reader spends against, or None if unlimited.

    :param permission: the reader's permission integer
    :type permission: int
    :param address: the address being watched
    :type address: str
    :param user_id: the reader's primary key
    :type user_id: int
    :return: str or None
    """
    band = terms(permission)
    if band is None:
        return None
    # An address is 58 base32 characters and can never begin `u:`, so the two
    # namespaces share a column without colliding.
    return address if band["keyed"] == "address" else f"u:{user_id}"


def is_free_tier(permission):
    """Return whether this reader is below the lowest paid tier.

    :param permission: the reader's permission integer
    :type permission: int
    :return: bool
    """
    return permission < SUBSCRIPTION_TIER_PERMISSIONS["Intro"]


def requires_linked_address(permission):
    """Return whether this reader may only watch addresses they have connected.

    :param permission: the reader's permission integer
    :type permission: int
    :return: bool
    """
    band = terms(permission)
    return bool(band and band["linked_only"])


def _stored(cache_client, key):
    """Return the decoded hash at `key`, or an empty dict."""
    raw = cache_client.hgetall(key) or {}
    return {
        (k.decode() if isinstance(k, bytes) else k): (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in raw.items()
    }


def _step(stored, now):
    """Return (seconds to add for this poll, the stored total before it).

    The first poll of a session charges nothing: there is no previous poll to
    measure from, and guessing would charge a reader for opening a page. That is
    also what makes switching live refresh off a pause rather than a decision -
    what is not polled is not charged, and coming back costs one `MAX_STEP`.
    """
    used, seen = 0.0, None
    try:
        used = float(stored.get("used", 0))
        seen = float(stored["seen"]) if stored.get("seen") else None
    except (TypeError, ValueError):
        used, seen = 0.0, None
    if seen is None:
        return 0.0, used
    # Never negative: a clock that steps backwards - an NTP correction, a
    # container clock - must not refund an allowance.
    return max(0.0, min(now - seen, MAX_STEP)), used


def spend(permission, address, user_id, cache_client, now):
    """Charge this poll to the reader's bucket and return what is left.

    None means unlimited, which is every tier from Asastatser up and costs
    neither a Redis round trip nor a query.

    **The database is touched at the edges of a session, never per poll.**
    Reading the row on every poll would make it the most-read row on the site
    for a number that changes by three seconds, which is the cost this two-layer
    arrangement exists to avoid. So the row is consulted when Redis has nothing -
    a new session, or an entry that aged out - and written only when
    `FLUSH_SECONDS` has accumulated or the bucket runs dry.

    :param permission: the reader's permission integer
    :type permission: int
    :param address: the address being watched
    :type address: str
    :param user_id: the reader's primary key
    :type user_id: int
    :param cache_client: Redis client instance
    :type cache_client: :class:`Redis`
    :param now: unix time of this poll
    :type now: float
    :return: float or None
    """
    band = terms(permission)
    if band is None:
        return None

    identity = bucket_key(permission, address, user_id)
    capacity = float(band["capacity"])
    per_second = band["per_week"] / WEEK
    key = f"{SPEND_KEY}:{identity}"
    stored = _stored(cache_client, key)
    step, used = _step(stored, now)

    balance = None
    if stored.get("balance") is not None:
        try:
            balance = float(stored["balance"])
        except (TypeError, ValueError):
            balance = None
    if balance is None:
        row, created = LiveAllowanceBucket.objects.get_or_create(
            key=identity,
            defaults={"balance": capacity, "capacity": capacity},
        )
        balance = capacity if created else row.current_balance(capacity, per_second)

    balance = max(0.0, balance - step)
    try:
        flushed = float(stored.get("flushed", 0)) + step
    except (TypeError, ValueError):
        flushed = step

    if flushed >= FLUSH_SECONDS or (balance <= 0 and step > 0):
        LiveAllowanceBucket.objects.update_or_create(
            key=identity,
            defaults={
                "balance": balance,
                "capacity": capacity,
                "modified": timezone.now(),
            },
        )
        flushed = 0.0

    cache_client.hset(
        key,
        mapping={
            "balance": balance,
            "seen": now,
            "flushed": flushed,
            "used": used + step,
        },
    )
    cache_client.expire(key, SPEND_TTL)
    return balance


def left(permission, address, user_id, cache_client):
    """Return what is left without spending any, or None when unlimited.

    Used to render the figure beside the button, which must not itself cost the
    reader time - a page that charges for being looked at would tick down while
    nothing moved.

    :param permission: the reader's permission integer
    :type permission: int
    :param address: the address being watched
    :type address: str
    :param user_id: the reader's primary key
    :type user_id: int
    :param cache_client: Redis client instance
    :type cache_client: :class:`Redis`
    :return: float or None
    """
    band = terms(permission)
    if band is None:
        return None

    identity = bucket_key(permission, address, user_id)
    stored = _stored(cache_client, f"{SPEND_KEY}:{identity}")
    if stored.get("balance") is not None:
        try:
            return max(0.0, float(stored["balance"]))
        except (TypeError, ValueError):
            pass
    row = LiveAllowanceBucket.objects.filter(key=identity).first()
    if row is None:
        return float(band["capacity"])
    return max(
        0.0, row.current_balance(float(band["capacity"]), band["per_week"] / WEEK)
    )

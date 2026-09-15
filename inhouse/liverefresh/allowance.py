"""How long a reader below the paid tiers may watch a page live, per day.

**A feature nobody has seen is a hard thing to sell.** The tier bands were
all-or-nothing: an authenticated reader below Asastatser got the 60-second page
reload and never saw what the subscription buys - figures moving in place while
scroll position, open rows and filters survive. Ten seconds of watching it makes
the argument that no pricing page can.

So every authenticated reader gets a daily allowance, and the paid tiers get what
they always had:

    authenticated, no tier    15 minutes a day
    Intro                     30 minutes a day
    Asastatser and above      unlimited

Anonymous readers get nothing, and that is the existing gate rather than a
decision taken here: `BaseUserPassesTestMixin` requires `is_authenticated`. An
allowance needs somewhere to keep a clock, and a cookie is a budget anyone can
reset.

**The clock lives in Redis, not in the profile.** A poll arrives every three
seconds per watching reader; a row write per poll would be the most-written row
on the site for a number nobody reads twice. The key expires, so a reader who
stops is forgotten rather than accumulated.

**What is charged is wall-clock, not polls.** Each poll charges the time since
that reader's *previous* poll, capped at `MAX_STEP`. Two consequences, both
wanted: a reader with four tabs open spends one second per second rather than
four, because their polls interleave and each charges the small gap since the
last one; and a reader who closes the laptop for an hour is charged the cap
rather than the hour, because they were not watching it.
"""

import datetime

from utils.constants.core import LIVEREFRESH_POLL_SECONDS
from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS

#: Hash holding one reader's spend. Fields: `day`, `used`, `seen`.
SPEND_KEY = "lvf"

#: Seconds a single poll may ever charge.
#:
#: Two poll intervals: enough that an ordinary gap - a slow block, a busy tab -
#: is charged honestly, and short enough that a reader returning after an hour
#: pays for the moment they came back rather than the hour they were away.
MAX_STEP = LIVEREFRESH_POLL_SECONDS * 2

#: How long a reader's spend is kept. Two days, so a clock started before
#: midnight is still there to be reset by the day check rather than vanishing
#: mid-session and handing out a second allowance.
SPEND_TTL = 60 * 60 * 48

#: Daily allowance in seconds, by the permission a reader holds. Ordered richest
#: first; the first band a reader clears is theirs, and `None` means unlimited.
DAILY_SECONDS = (
    (SUBSCRIPTION_TIER_PERMISSIONS["Asastatser"], None),
    (SUBSCRIPTION_TIER_PERMISSIONS["Intro"], 30 * 60),
    (0, 15 * 60),
)


def daily_allowance(permission):
    """Return the seconds `permission` may watch per day, or None for unlimited.

    :param permission: the reader's permission integer
    :type permission: int
    :return: int or None
    """
    for required, seconds in DAILY_SECONDS:
        if permission >= required:
            return seconds
    return 0


def _today(now):
    return datetime.datetime.fromtimestamp(now, datetime.timezone.utc).strftime(
        "%Y-%m-%d"
    )


def charge(user_id, cache_client, now):
    """Add this poll's watching time to `user_id`'s day, and return the total.

    The first poll of a day charges nothing: there is no previous poll to
    measure from, and guessing would charge a reader for opening a page.

    :param user_id: the reader's primary key
    :type user_id: int
    :param cache_client: Redis client instance
    :type cache_client: :class:`Redis`
    :param now: unix time of this poll
    :type now: float
    :return: float, seconds spent today including this poll
    """
    key = f"{SPEND_KEY}:{user_id}"
    raw = cache_client.hgetall(key) or {}
    stored = {
        (k.decode() if isinstance(k, bytes) else k): (
            v.decode() if isinstance(v, bytes) else v
        )
        for k, v in raw.items()
    }

    today = _today(now)
    used, seen = 0.0, None
    if stored.get("day") == today:
        try:
            used = float(stored.get("used", 0))
            seen = float(stored["seen"]) if stored.get("seen") else None
        except (TypeError, ValueError):
            used, seen = 0.0, None

    if seen is not None:
        # Never negative: a clock that steps backwards - an NTP correction, a
        # container clock - must not refund an allowance.
        used += max(0.0, min(now - seen, MAX_STEP))

    cache_client.hset(key, mapping={"day": today, "used": used, "seen": now})
    cache_client.expire(key, SPEND_TTL)
    return used


def remaining(permission, user_id, cache_client, now):
    """Return the seconds left today, or None when the reader is unlimited.

    **Unlimited readers are not metered at all**, which is the common case for
    anyone the feature is actually sold to - so the paid path costs no Redis
    round trip that it did not already make.

    :param permission: the reader's permission integer
    :type permission: int
    :param user_id: the reader's primary key
    :type user_id: int
    :param cache_client: Redis client instance
    :type cache_client: :class:`Redis`
    :param now: unix time of this poll
    :type now: float
    :return: float or None
    """
    allowed = daily_allowance(permission)
    if allowed is None:
        return None
    return allowed - charge(user_id, cache_client, now)

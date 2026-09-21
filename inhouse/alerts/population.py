"""Telling the engine which pages have rules on them.

**A fourth set beside `lvx`, `lvq` and `lva`**, and the website publishes it the
same way the live-refresh widget publishes the first two - `zadd` straight onto
the engine's Redis, with the key named here and documented there. See
`notifications/DESIGN.md`.

**The difference that matters: this one is not heartbeat-scored.** The other
three age out about ninety seconds after the last poll, because they answer "who
is looking right now". An alert exists for when nobody is looking, so a page
stays here until the last rule naming it is removed. The score is the moment the
page last gained a rule; it is written for whoever is reading the set by hand
and is never used to expire anything.

**Nothing here may break a request.** A reader writing a rule has done something
that must be stored; whether the engine has yet been told is a separate concern,
and a Redis that is briefly away is not a reason to refuse the rule. Every
failure is logged and swallowed, and the next write repairs the set.
"""

import logging
import time

from utils.clients import redis_instance

logger = logging.getLogger(__name__)

#: Sorted set of pages with at least one active rule.
#:
#: Read by the engine's live pass, which walks `lvx ∪ lvq ∪ lva ∪ lvr`. Named
#: here as a literal for the same reason `liverefresh` names `lvx` as one: the
#: two projects share a Redis rather than a codebase, and the engine's
#: `CACHE_KEY_LIVE_RULES` is the other half of this contract.
RULES_KEY = "lvr"


def publish_page(address, client=None):
    """Add or remove `address` in `lvr` according to whether a rule names it.

    **Recomputed rather than counted up and down.** An incrementing membership
    would drift the first time a rule was deleted by a path that forgot to
    decrement - and the failure is invisible, because a page wrongly present is
    merely re-priced for nobody, while a page wrongly absent is alerts that
    never fire. Asking the database is cheap and cannot drift.

    :param address: the bundle or address the rules name
    :type address: str
    :param client: an open Redis client, or None to make one
    :return: True when the page is now in the set, False when it is not, and
        None when the set could not be reached
    :rtype: bool or None
    """
    if not address:
        return None

    from .models import AlertRule  # noqa: PLC0415 - avoids an import cycle

    wanted = AlertRule.objects.filter(address=address, active=True).exists()
    try:
        client = client or redis_instance()
        if wanted:
            client.zadd(RULES_KEY, {address: int(time.time())})
        else:
            client.zrem(RULES_KEY, address)
    except Exception as error:  # noqa: BLE001 - see the module docstring
        logger.warning("could not publish the alert population: %s", error)
        return None
    return wanted


def published_pages(client=None):
    """Return the pages currently published, for checking by hand.

    Not used by the widget. It exists because "is this page in `lvr`" is the
    first question anybody debugging an alert that did not fire will ask, and
    the alternative is a `redis-cli` incantation with the password in it.

    :param client: an open Redis client, or None to make one
    :return: the addresses in the set, or an empty tuple when unreachable
    :rtype: tuple
    """
    try:
        client = client or redis_instance()
        return tuple(
            member.decode() if isinstance(member, bytes) else member
            for member in client.zrange(RULES_KEY, 0, -1)
        )
    except Exception as error:  # noqa: BLE001 - see the module docstring
        logger.warning("could not read the alert population: %s", error)
        return ()

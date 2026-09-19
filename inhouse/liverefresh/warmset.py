"""How many addresses one reader may keep warm, across every surface at once.

**The tier bands are enforced per page today, not per reader.** `can_access` is
asked once per request with *that page's* address count, and `lvx` is keyed by
the address string alone with no reader in it - so nothing can count how many
pages one person is watching. Five tabs of one address each is five size-1
checks that all pass, which happens to land on the intended five; five tabs of
five-address bundles is also five passing checks, and twenty-five addresses
re-priced every block on a plan that sold five. `widget.toml` records this as a
known hole and says what closing it needs: the subscription set has to know
*who* is watching.

This is that, kept deliberately on the frontend side.

**Members are addresses, not pages, and that is the whole point.** The resource
is *distinct addresses kept warm*, so a reader with `{A, B, C}` open in a
browser and an API call for `{C, D}` costs **four**, not five. Keying by page
string would bill `C` twice, and fetching by API the same bundle you are
watching is the single most likely thing a subscriber does.

**Do not put the reader into `lvx`.** The engine reads that key and has no idea
who a reader is - `_admit`'s own docstring says so, which is why the paid set
`lvq` had to be a separate key rather than a flag on `lvx`. This set decides
what gets written to `lvx` at all; the engine's view of the world is unchanged.

**The two surfaces want opposite things when the budget is full**, and that
asymmetry is what makes a shared budget shippable:

* the **browser evicts** its least-recently-touched address and never refuses.
  Live refresh already degrades this way - `_admit` sheds and the reader sees
  what a non-subscriber sees - and a page quietly going static is a far better
  failure than an error on a tab they are probably not looking at;
* the **API refuses**, because a machine consumer wants a status code rather
  than data that is quietly less fresh than it asked for.

Ageing matches `lvx` exactly: a member scored with the unix time it was last
touched, and anything older than `LIVE_SUBSCRIPTION_SECONDS` is not warm. The
engine leaves its own stale members in place and filters by score on read,
because it only reads. This key is read *and* written here, so it trims itself.
"""

from utils.constants.core import LIVEREFRESH_SUBSCRIPTION_SECONDS

#: Prefix for one reader's warm set. Suffixed with the user's primary key.
#: Members are single addresses, scored by the unix time each was last touched.
WARM_PREFIX = "lvw"

#: How long a touch keeps an address warm. The same window the engine applies
#: to `lvx`, so an address stops counting against a reader at the same moment
#: it stops being re-priced for them.
WARM_SECONDS = LIVEREFRESH_SUBSCRIPTION_SECONDS

#: How long the key itself survives with nothing touching it. Comfortably more
#: than the window, so the set outlives a slow poll and still disappears for a
#: reader who has gone.
WARM_TTL = WARM_SECONDS * 4


def key_for(user_pk):
    """Return the Redis key holding this reader's warm set.

    :param user_pk: the reader's primary key
    :type user_pk: int
    :return: str
    """
    return f"{WARM_PREFIX}:{user_pk}"


def cap_for(permission, required_permission):
    """Return how many addresses `permission` may keep warm at once.

    **Read from the manifest's own bands rather than a second list**, so the
    numbers have one source of truth and a tier change cannot land in one place
    and not the other.

    The bands answer "what permission is needed for this many addresses"; the
    cap is the reverse question, so this takes the widest band the reader
    actually clears. A manifest with a plain integer permission is not banded at
    all and has no cap.

    :param permission: the reader's permission integer
    :type permission: int
    :param required_permission: integer or ordered band list from the manifest
    :type required_permission: int or list
    :var allowed: widths of every band this reader clears
    :type allowed: list
    :return: int or None
    """
    if isinstance(required_permission, int):
        return None
    allowed = [
        band["max_addresses"]
        for band in required_permission
        if permission >= band["permission"]
    ]
    return max(allowed) if allowed else 0


def count(user_pk, client, now):
    """Return how many addresses this reader currently has warm.

    Trims what has aged out first, so the answer is the live figure rather than
    everything ever touched.

    :param user_pk: the reader's primary key
    :type user_pk: int
    :param client: Redis client instance
    :type client: :class:`Redis`
    :param now: unix time to judge staleness against
    :type now: float
    :return: int
    """
    key = key_for(user_pk)
    client.zremrangebyscore(key, 0, now - WARM_SECONDS)
    return client.zcard(key)


def members(user_pk, client, now):
    """Return the addresses this reader currently has warm, freshest last.

    :param user_pk: the reader's primary key
    :type user_pk: int
    :param client: Redis client instance
    :type client: :class:`Redis`
    :param now: unix time to judge staleness against
    :type now: float
    :return: list
    """
    key = key_for(user_pk)
    client.zremrangebyscore(key, 0, now - WARM_SECONDS)
    return [
        member.decode() if isinstance(member, bytes) else member
        for member in client.zrange(key, 0, -1)
    ]


def touch(user_pk, addresses, cap, client, now, evict=True):
    """Keep `addresses` warm for this reader, and report what did not fit.

    Returns `(admitted, evicted)` - the addresses that are warm for this reader
    after the call, and the ones dropped to make room. `evicted` is always empty
    when `evict` is False; `admitted` is then empty if the request did not fit,
    because a refusal must not half-admit a bundle and leave the caller guessing
    which half it got.

    **A cap of None is unlimited** and costs one round trip rather than a branch
    at every call site.

    **Not transactional, deliberately.** Two polls from the same reader racing
    can briefly leave the set one over its cap, and the next call trims it. The
    alternative is a watch/multi retry loop on the hottest path in the widget,
    to bound a number that is already bounded by `_admit` on the engine side -
    this decides what a reader may *ask* for, not what the engine will *do*.

    :param user_pk: the reader's primary key
    :type user_pk: int
    :param addresses: the addresses this surface wants warm
    :type addresses: list
    :param cap: how many this reader may keep warm, or None for unlimited
    :type cap: int or None
    :param client: Redis client instance
    :type client: :class:`Redis`
    :param now: unix time to score the touch with
    :type now: float
    :param evict: drop the least-recently-touched to make room, rather than
        refusing - True for the browser, False for the API
    :type evict: bool
    :var wanted: the union of what is already warm and what was asked for
    :type wanted: set
    :return: tuple
    """
    key = key_for(user_pk)
    addresses = [address for address in addresses if address]
    if not addresses:
        return [], []

    client.zremrangebyscore(key, 0, now - WARM_SECONDS)

    if cap is None:
        client.zadd(key, dict.fromkeys(addresses, now))
        client.expire(key, WARM_TTL)
        return list(addresses), []

    if cap <= 0:
        return [], []

    held = set(members(user_pk, client, now))
    # The union is the accounting, and it is why members are addresses: an
    # address already warm for this reader costs nothing to ask for again.
    wanted = held | set(addresses)

    if not evict and len(wanted) > cap:
        # Refuse whole. Touching the ones that happen to fit would admit part
        # of a bundle and leave the caller with an answer about addresses it
        # did not ask about on their own.
        return [], []

    client.zadd(key, dict.fromkeys(addresses, now))
    client.expire(key, WARM_TTL)

    evicted = []
    over = client.zcard(key) - cap
    if over > 0:
        # Lowest scores are the least recently touched, which is the tab the
        # reader is least likely to be looking at.
        evicted = [
            member.decode() if isinstance(member, bytes) else member
            for member in client.zrange(key, 0, over - 1)
        ]
        client.zremrangebyrank(key, 0, over - 1)

    return [
        address for address in addresses if address not in set(evicted)
    ], evicted

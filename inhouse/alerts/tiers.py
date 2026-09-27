"""What each subscription tier may watch: how many rules, which subjects, how
many pages.

**Written out rather than derived, and that is deliberate.** `api/tiers.py`
records the reason at length: this project has twice conflated two tier axes
that happen to share tier names. `ALERT_PAGES_PER_TIER` matching the
`liverefresh` bands 1 / 5 / 20 is on purpose - the same quantity, bought twice -
but an alert page never expires while a watched address stops costing anything
when the tab closes, so either may change without the other and neither imports
from the other.

**Three tables because there are three costs**, measured 2026-09-27: a priced
subject is answered per *asset* by a task that runs 288 times a day however many
readers ask; every other subject pins the reader's page into the engine's live
pass, which is about 29,000 website requests a day per page, for ever. Rows
themselves are free. See docs/logbook.md and
`post-deploy/alerts-tier-analysis.md`.

Set by the account holder, 2026-09-21; opened to price-only rules below
Asastatser on 2026-09-27.
"""

from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS

#: Rules a tier may keep, by tier name.
#:
#: Trial and Intro keep price-only rules - see `ALERT_SUBJECTS_PER_TIER`. They
#: were zero until 2026-09-27, when the measurement showed a price rule costs
#: nothing per reader; what a subscription buys is the page half.
ALERT_RULES_PER_TIER = {
    "Trial": 2,
    "Intro": 5,
    "Asastatser": 5,
    "Professional": 25,
    "Cluster": 50,
}

#: Subjects a tier may write a rule on, by tier name.
#:
#: **The two halves of this feature cost three orders of magnitude apart.** A
#: priced subject is answered per *asset*, shared by every reader, by a task that
#: runs 288 times a day however many rules exist. Every other subject puts the
#: reader's page in `lvr`, which the engine's live pass then values every block
#: and which never ages out. So the unpaid tiers get the priced half, and it is a
#: whole feature rather than a crippled one: threshold, direction, cooldown,
#: notification and browser permission all work.
#:
#: Resolved lazily in :func:`subjects_allowed` - a tier table is imported while
#: the app registry is still loading.
ALERT_SUBJECTS_PER_TIER = {
    "Trial": "priced",
    "Intro": "priced",
    "Asastatser": "all",
    "Professional": "all",
    "Cluster": "all",
}

#: Distinct pages a tier may keep page-subject rules on, by tier name.
#:
#: **The cap that matches the cost.** `ALERT_RULES_PER_TIER` counts rules, and
#: twenty-five rules on one page cost what one does while twenty-five rules on
#: twenty-five pages cost twenty-five times as much - the live pass charges per
#: page, per block, for ever. These are deliberately the `liverefresh` bands,
#: 1 / 1 / 5 / 20: the same quantity, bought twice, and the alert is the dearer
#: of the two because it does not expire when the reader closes the tab.
ALERT_PAGES_PER_TIER = {
    "Trial": 0,
    "Intro": 0,
    "Asastatser": 1,
    "Professional": 5,
    "Cluster": 20,
}


def _tier_name(permission):
    """Return the name of the band `permission` falls in.

    **Descending, so an unknown permission lands on the band below it** rather
    than on zero. A permission between two tiers is a tier the table does not
    name, and answering "none" for one would take a paying reader's alerts away
    on a day nobody deployed anything.

    :param permission: the profile's permission value
    :type permission: int
    :return: the tier's name, "Trial" below every paid tier
    :rtype: str
    """
    for name, floor in sorted(
        SUBSCRIPTION_TIER_PERMISSIONS.items(), key=lambda item: -item[1]
    ):
        if permission >= floor:
            return name
    return "Trial"


def rules_allowed(permission):
    """Return how many rules a profile at `permission` may keep.

    :param permission: the profile's permission value
    :type permission: int
    :return: how many rules are allowed
    :rtype: int
    """
    return ALERT_RULES_PER_TIER.get(_tier_name(permission), 0)


def subjects_allowed(permission):
    """Return the subjects a profile at `permission` may write a rule on.

    :param permission: the profile's permission value
    :type permission: int
    :return: the subject values, as strings
    :rtype: frozenset
    """
    from .models import PAGE_SUBJECTS, PRICED_SUBJECTS  # noqa: PLC0415

    priced = frozenset(str(subject) for subject in PRICED_SUBJECTS)
    if ALERT_SUBJECTS_PER_TIER.get(_tier_name(permission)) == "all":
        return priced | frozenset(str(subject) for subject in PAGE_SUBJECTS)
    return priced


def pages_allowed(permission):
    """Return how many distinct pages a profile may keep page rules on.

    :param permission: the profile's permission value
    :type permission: int
    :return: how many pages are allowed, zero below Asastatser
    :rtype: int
    """
    return ALERT_PAGES_PER_TIER.get(_tier_name(permission), 0)


def more_rules_available(permission):
    """Whether any tier keeps more rules than the one at `permission`.

    **The top band has nowhere to be sent.** A reader who has spent a Cluster
    allowance is at the largest number this site sells, and offering them a link
    to the plans page is an invitation to pay for something they already have -
    which reads, correctly, as the site not knowing what they bought.

    Derived from the table rather than naming the top tier, so a band added
    above `Cluster` needs no change here and one removed cannot leave this
    pointing at a tier that no longer exists.

    :param permission: the profile's permission value
    :type permission: int
    :return: Boolean
    """
    return rules_allowed(permission) < max(ALERT_RULES_PER_TIER.values())

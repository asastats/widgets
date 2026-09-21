"""How many alert rules each subscription tier may keep.

**Written out rather than derived, and that is deliberate.** `api/tiers.py`
records the reason at length: this project has twice conflated two tier axes
that happen to share tier names, once in the widget runbook and once in
`live/API-TIERS.md`. The `liverefresh` widget bands how many *addresses* a
reader may watch; this bands how many *rules* they may keep. The numbers are
unrelated and importing one from the other would make a later change to either
silently move the other.

**The axis this bounds is evaluation, not storage.** A rule costs a row and one
comparison per tick against a number the live pass has already computed - see
`notifications/DESIGN.md`. Rows are free; the count matters because the per-asset
half of the evaluator refreshes the union of assets named in active rules, so
every rule on a thinly-held asset is an asset somebody has to keep fresh.

Set by the account holder, 2026-09-21.
"""

from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS

#: Rules a tier may keep, by tier name.
#:
#: Trial and Intro are zero: alerts are a paid feature, and a control that is
#: rendered dead teaches a reader the feature does not work rather than that it
#: costs something. The gate is on the control, the way the fold sizes and the
#: typeface picker already do it - below the tier it is a link to subscriptions.
ALERT_RULES_PER_TIER = {
    "Trial": 0,
    "Intro": 0,
    "Asastatser": 5,
    "Professional": 25,
    "Cluster": 50,
}


def rules_allowed(permission):
    """Return how many rules a profile at `permission` may keep.

    **Descending, so an unknown permission lands on the band below it** rather
    than on zero. A permission between two tiers is a tier the table does not
    name, and answering "none" for one would take a paying reader's alerts away
    on a day nobody deployed anything.

    :param permission: the profile's permission value
    :type permission: int
    :return: how many rules are allowed, zero if below every paid tier
    :rtype: int
    """
    for name, floor in sorted(
        SUBSCRIPTION_TIER_PERMISSIONS.items(), key=lambda item: -item[1]
    ):
        if permission >= floor:
            return ALERT_RULES_PER_TIER.get(name, 0)
    return ALERT_RULES_PER_TIER["Trial"]

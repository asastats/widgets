"""Module containing historic widget's prmission functions."""

from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS

TIERS_ADDRESSES_LIMIT = {
    "Intro": 0,
    "Asastatser": 1,
    "Professional": 5,
    "Cluster": 10,
}
ADDRESSES_LIMIT_ERROR = (
    "Your <a href='/subscriptions/' target='_blank' rel='noopener'>subscription tier"
    "</a> allows you to evaluate historic data for up to %s address(es)."
)

def can_access(profile, size):
    """Return True if user is allowed to access historic widget for `size`.

    :param profile: user's profile instance
    :type profile: :class:`core.models.Profile`
    :param size: number of Algorand addresses in the bundle
    :type size: int
    :return: Boolean
    """
    if size > TIERS_ADDRESSES_LIMIT.get("Cluster"):
        return False

    if size > TIERS_ADDRESSES_LIMIT.get("Professional"):
        return (
            True
            if profile.permission >= SUBSCRIPTION_TIER_PERMISSIONS.get("Cluster")
            else False
        )

    if size > TIERS_ADDRESSES_LIMIT.get("Asastatser"):
        return (
            True
            if profile.permission >= SUBSCRIPTION_TIER_PERMISSIONS.get("Professional")
            else False
        )

    return (
        True
        if profile.permission >= SUBSCRIPTION_TIER_PERMISSIONS.get("Asastatser")
        else False
    )

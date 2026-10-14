"""What each subscription tier gets from the profit and loss widget."""

from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS


def is_subscriber(permission):
    """Return whether `permission` is Asastatser or above.

    :param permission: profile's permission value
    :type permission: int
    :return: Boolean
    """
    return (permission or 0) >= SUBSCRIPTION_TIER_PERMISSIONS["Asastatser"]


def features_for(permission):
    """Return the widget features `permission` unlocks.

    :param permission: profile's permission value
    :type permission: int
    :var subscriber: Asastatser or above
    :type subscriber: Boolean
    :var professional: Professional tier or above
    :type professional: Boolean
    :var cluster: Cluster tier
    :type cluster: Boolean
    :return: dict
    """
    subscriber = is_subscriber(permission)
    professional = (permission or 0) >= SUBSCRIPTION_TIER_PERMISSIONS["Professional"]
    cluster = (permission or 0) >= SUBSCRIPTION_TIER_PERMISSIONS["Cluster"]
    return {
        "linked_only": not subscriber,
        "currencies": ("usd", "algo") if subscriber else ("usd",),
        "drilldown": subscriber,
        "periods": ("all", "ytd", "30d", "7d") if subscriber else ("all",),
        "valuations": ("spot", "mve") if professional else ("spot",),
        "lp_analytics": cluster,
    }

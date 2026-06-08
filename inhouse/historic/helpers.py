"""Deterministic helpers vendored from the engine.

These must stay equivalent to the engine's implementations so the widget and the
engine agree without the widget importing engine code. ``BARS_COUNT`` here must
equal the engine's ``HISTORIC_WIDGET_BARS_COUNT`` and ``QUARTER`` must equal the
engine's ``QUARTER``; otherwise zoom clamping would diverge between the two sides.
``group_name_from_bundle`` must match the engine's so both resolve the identical
shared Channels group.
"""

from .constants import BARS_COUNT

QUARTER = 0.72


def group_name_from_bundle(bundle, prefix="historic"):
    """Return consumer group name for provided `bundle`.

    :param bundle: hash made from provided addresses
    :type bundle: str
    :param prefix: channel group name prefix
    :type prefix: str
    :return: str
    """
    return f"{prefix}_{bundle}"


def check_chart_period(period):
    """Return adjusted period if provided `period` is too small.

    :param period: chart's minimum and maximum timestamp
    :type period: two-tuple
    :var interval: duration between two adjacted bars
    :type interval: float
    :return: two-tuple
    """
    interval = (period[1] - period[0]) / BARS_COUNT
    if interval < 4 * QUARTER:
        return (
            period[0],
            int(period[0] + 4 * QUARTER * BARS_COUNT),
        )
    return period

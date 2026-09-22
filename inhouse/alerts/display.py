"""How a rule reads to the person who made it.

**Separate from `AlertRule.__str__`, and deliberately.** The model's own text is
the technical one - the page as it is stored, the threshold at the column's full
scale - and it has to stay that way: `__str__` is what the admin renders for
every row at once, and it must not reach Redis or fail. Everything here may do
both, because it runs for a panel a reader opened or a notification about to be
sent.

Two things it fixes, both reported from the running site:

**A page is stored as a bundle even when it is one address.** Every alert is
made on a page, and a page is a bundle by construction - so a reader who set a
rule on their own address was told about
``86C2B129E807A583C4D37BA182B4EC26F64B3CC9``, which is a hash of the address
they were looking at. Resolved back here: one address in the bundle means the
reader meant that address, and that is what they are shown.

**A threshold is stored at ten decimal places.** "falls below 100.0000000000" is
the column's scale leaking into a sentence. The reader typed "100".
"""

import logging
from decimal import Decimal, InvalidOperation

from .models import PERCENT_SUBJECTS, Subject

logger = logging.getLogger(__name__)

#: Decimals for a figure in ALGO or USD - a total, or a holding's value.
#:
#: Two, and trailing zeros kept: "100.00 ALGO" is how money reads, and trimming
#: it to "100" makes a total look like a count.
VALUE_DECIMALS = 2

#: Decimals for a price, before trailing zeros are dropped.
#:
#: More than a value gets, because an ASA price is routinely smaller than a
#: cent and two places would render most of them "0.00" - a threshold that says
#: the asset is worthless. Six covers the ordinary range; below that
#: :data:`STORED_DECIMALS` takes over.
PRICE_DECIMALS = 6

#: The scale the column itself keeps, and so the most that can be claimed.
#:
#: `AlertRule.threshold` is `decimal_places=10`. A price too small for
#: :data:`PRICE_DECIMALS` is shown at this scale rather than as "0" - never
#: beyond it, which would be inventing precision the row does not hold.
STORED_DECIMALS = 10


def format_value(amount):
    """Return `amount` as a figure in ALGO or USD.

    :param amount: the figure
    :type amount: decimal.Decimal or float
    :return: str
    """
    return f"{_number(amount):.{VALUE_DECIMALS}f}"


def format_price(amount):
    """Return `amount` as a price, without trailing zeros.

    :param amount: the price
    :type amount: decimal.Decimal or float
    :return: str
    """
    amount = _number(amount)
    text = _trimmed(amount, PRICE_DECIMALS)
    if amount and not _is_zero(text):
        return text
    # **Smaller than six places is a real ASA price, not a zero.** Rounding one
    # away would show a threshold the reader never chose, and "0" is the single
    # most misleading thing this could print: it reads as an asset worth
    # nothing rather than an asset worth very little.
    return _trimmed(amount, STORED_DECIMALS) if amount else text


def format_percent(amount):
    """Return `amount` as a percentage, without trailing zeros.

    :param amount: the move, unsigned as the reader stored it
    :type amount: decimal.Decimal or float
    :return: str
    """
    return f"{_trimmed(amount, VALUE_DECIMALS)}%"


def _number(amount):
    """Return `amount` as a Decimal, whatever it arrived as.

    **A threshold is not always a Decimal, and the difference does not show.**
    Django casts it on the way out of the database, so a rule read back is one -
    but the instance a form just saved still holds the string that was posted,
    and that is the instance the panel re-renders and the notification is built
    from. Formatting it raises `ValueError: Unknown format code` at exactly the
    moment a reader adds a rule, and never in a test that fetched one.

    :param amount: the figure, as a Decimal, float, int or string
    :return: :class:`decimal.Decimal`
    """
    if isinstance(amount, Decimal) and amount.is_finite():
        return amount
    try:
        parsed = Decimal(str(amount))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0)
    # **NaN and Infinity parse, and then format as themselves.** `Decimal("NaN")`
    # is a perfectly good Decimal that renders "NaN ALGO" in a notification -
    # which is the one outcome worse than a wrong number, because it reads as
    # the site being broken rather than as a figure to check.
    return parsed if parsed.is_finite() else Decimal(0)


def _trimmed(amount, decimals):
    """Return `amount` at `decimals` places with trailing zeros removed.

    :param amount: the figure
    :param decimals: how many places to render before trimming
    :type decimals: int
    :return: str
    """
    text = f"{_number(amount):.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _is_zero(text):
    """Whether `text` rendered to nothing but zero.

    :param text: a formatted figure
    :type text: str
    :return: Boolean
    """
    return text.lstrip("-") in ("", "0")


def page_label(address):
    """Return how to name the page `address` watches.

    **One address in the bundle means the reader meant that address.** Alerts
    are made on a page and every page is a bundle, so a rule set on a single
    address is stored under a hash of it - which is correct, and unreadable.

    Never raises and never returns nothing: this runs while rendering a panel
    and while building a notification, and neither has anywhere to put a
    failure. An unresolvable bundle is shown as itself, shortened.

    :param address: the bundle or address the rule names
    :type address: str
    :return: str
    """
    from core.templatetags.core_extras import short_address  # noqa: PLC0415

    # Coerced rather than guarded: `short_address` slices, so anything that is
    # not a string raises there instead of here. A `try` around it would be a
    # branch nothing can reach - `AlertRule.address` is a `CharField` - and an
    # unreachable branch is worse than the one line that makes it impossible.
    address = str(address or "")
    if not address:
        return ""
    return short_address(_sole_address(address) or address)


def _sole_address(address):
    """Return the one address in `address`'s bundle, or None.

    None covers all three "not one address": a bundle of several, a bundle the
    cache cannot resolve, and a cache that is away. The caller falls back to the
    stored value in every one of them.

    :param address: the bundle or address the rule names
    :type address: str
    :return: str or None
    """
    # Imported here rather than at module scope: this widget is tested from the
    # standalone widgets repo too, where the host is not importable, and the
    # import must not be what decides whether the module loads.
    from api.widgets import bundle_and_addresses_from_path  # noqa: PLC0415

    try:
        _, addresses = bundle_and_addresses_from_path(
            address, force_bundle=False
        )
    except Exception as error:  # noqa: BLE001 - see the docstring
        logger.warning("could not resolve %s: %s", address, error)
        return None

    parts = (addresses or "").split()
    return parts[0] if len(parts) == 1 else None


def describe(rule):
    """Return the sentence a reader is shown for `rule`.

    Used by the panel's list and by the notification body, so that what a reader
    agreed to and what arrives on their phone are the same words.

    :param rule: the rule
    :type rule: :class:`widgets.inhouse.alerts.models.AlertRule`
    :return: str
    """
    if rule.subject in PERCENT_SUBJECTS:
        amount = format_percent(rule.threshold)
    elif rule.subject == Subject.ASA_PRICE:
        amount = f"{format_price(rule.threshold)} ALGO"
    else:
        # A total or a holding's value. Both are ALGO, as every threshold is
        # stored - the ALGO/USD control converts on the way in, not on the way
        # out, so there is no dollar figure here to show.
        amount = f"{format_value(rule.threshold)} ALGO"

    target = rule.asset_id if rule.needs_asset else page_label(rule.address)
    return (
        f"{rule.get_subject_display()} {target} "
        f"{rule.get_direction_display().lower()} {amount}"
    )

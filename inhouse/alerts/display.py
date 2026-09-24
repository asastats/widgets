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

from .models import AMOUNT_SUBJECTS, PERCENT_SUBJECTS, Subject

#: How each subject reads *inside a sentence*, with the thing it watches in
#: it.
#:
#: **Not `get_subject_display()`.** Those labels are picker options - they
#: answer "what do you want to watch?" - and dropped into a sentence they
#: name the asset where the option already said "an asset". The picker keeps
#: its labels and a sentence gets its own phrasing, with one slot for the
#: thing being watched.
SENTENCES = {
    Subject.ASA_PRICE: "{target} price",
    Subject.ASA_PRICE_PERCENT: "{target} price change",
    Subject.ASA_AMOUNT: "My {target} holding",
    Subject.ASA_TOTAL: "My {target} holding's value",
    Subject.TOTAL_VALUE: "Portfolio total for {target}",
    Subject.TOTAL_PERCENT: "Portfolio total change for {target}",
}

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
    # **Smaller than six places is a real ASA price, not a zero.** Rounding
    # one away prints "0", which reads as an asset worth nothing rather than
    # one worth very little.
    return _trimmed(amount, STORED_DECIMALS) if amount else text


def format_count(amount):
    """Return `amount` as a count of an asset, grouped for reading.

    **Grouped, because a count is the one figure here that gets long.** A
    million of a token rendered "1000000" is a number a reader has to count the
    digits of; "1,000,000" is one they can see. Values and prices are not
    grouped - a price is small by nature and a value is money the rest of the
    site renders ungrouped - so this is its own formatter rather than a flag on
    another one.

    Trailing zeros dropped first: a whole number of tokens should not read
    "1,000,000.000000".

    **No guard around `int()`, because there is nothing it could catch.**
    `_number` answers a finite `Decimal` for everything - NaN, Infinity, None
    and a junk string all come back as one - and `_trimmed` renders that with
    `:.6f`, which yields an optional minus sign and digits and never an
    exponent. So the whole part is always something `int` accepts. That was
    checked by running every one of those through it rather than by reading
    the code, after a `try` here sat uncovered and a test for it would have had
    to fake an input production cannot produce.

    :param amount: the count, in whole units as the reader typed it
    :type amount: decimal.Decimal or float
    :return: str
    """
    text = _trimmed(_number(amount), PRICE_DECIMALS)
    whole, _, fraction = text.partition(".")
    whole = f"{int(whole):,}"
    return f"{whole}.{fraction}" if fraction else whole


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
    # **NaN and Infinity parse, and then format as themselves.**
    # `Decimal("NaN")` renders "NaN ALGO" in a notification, which reads as the
    # site being broken rather than as a figure to check.
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

    # Coerced rather than guarded: `AlertRule.address` is a `CharField`, so a
    # `try` here would be a branch nothing can reach.
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
    # **Imported here, not at module scope**: this widget is also tested from
    # the standalone widgets repo, where the host is not importable.
    from api.widgets import bundle_and_addresses_from_path  # noqa: PLC0415

    try:
        _, addresses = bundle_and_addresses_from_path(address, force_bundle=False)
    except Exception as error:  # noqa: BLE001 - see the docstring
        logger.warning("could not resolve %s: %s", address, error)
        return None

    parts = (addresses or "").split()
    return parts[0] if len(parts) == 1 else None


def disclosure(depth_algo):
    """Return what to tell a reader about the liquidity behind a price.

    **Told rather than judged, and this is the decision.** A price from pools
    holding a few hundred ALGO moves several percent on one ordinary swap and
    back again, so a rule watching it fires on noise that reads - in a
    notification - exactly like news. The alternatives were to refuse such a
    rule or to suppress it silently; both make us pick a liquidity threshold on
    the reader's behalf, and a rule that stops firing without saying why is the
    same class of mistake as one that means something other than what it says.

    **ALGO rather than units of the asset.** "Pools hold 4,000,000 units" says
    nothing without knowing what a unit is worth.

    Nothing is said when the depth is unknown. A missing measurement is not a
    small one, and inventing "0 ALGO" would read as a finding.

    :param depth_algo: what the asset's pools hold, valued in ALGO
    :type depth_algo: float or None
    :return: str
    """
    if not depth_algo:
        return ""
    return f"pools hold ~{format_value(depth_algo)} ALGO"


def asset_label(rule):
    """Return how to name the asset a rule watches.

    **The unit the reader picked, falling back to the id.** "an asset
    31566704" is what every notification said until the unit was stored, and
    the id is not what a reader recognises - they chose "USDC" out of a picker
    that showed them that word.

    The fallback is not decoration: a rule written before the unit was stored,
    or by a client that did not send one, still has to describe itself. It
    carries a `#` so that the sentence reads as an asset id rather than as a
    bare number sitting where a name belongs.

    :param rule: the rule
    :type rule: :class:`widgets.inhouse.alerts.models.AlertRule`
    :return: str
    """
    unit = (rule.asset_unit or "").strip()
    return unit or f"#{rule.asset_id}"


def subject_phrase(rule):
    """Return how `rule`'s subject reads in front of its direction.

    A subject with no sentence form falls back to its picker label, which is
    the behaviour this replaced: clumsy, and never wrong.

    :param rule: the rule
    :type rule: :class:`widgets.inhouse.alerts.models.AlertRule`
    :return: str
    """
    target = asset_label(rule) if rule.needs_asset else page_label(rule.address)
    form = SENTENCES.get(rule.subject)
    return (
        form.format(target=target) if form else (f"{rule.get_subject_display()} {target}")
    )


def describe(rule):
    """Return the sentence a reader is shown for `rule`.

    Used by the panel's list and by the notification body, so that what a reader
    agreed to and what arrives on their phone are the same words.

    :param rule: the rule
    :type rule: :class:`widgets.inhouse.alerts.models.AlertRule`
    :return: str
    """
    currency = "USD" if rule.threshold_unit == "usd" else "ALGO"
    if rule.subject in PERCENT_SUBJECTS:
        amount = format_percent(rule.threshold)
    elif rule.subject in AMOUNT_SUBJECTS:
        # A count in the asset's own units. **The unit is not repeated** - the
        # subject already names the asset - and there is no currency, because
        # "I hold more than a million" is true whatever one is worth.
        amount = format_count(rule.threshold)
    elif rule.subject == Subject.ASA_PRICE:
        amount = f"{format_price(rule.threshold)} {currency}"
    else:
        # **Named in the reader's own currency**, which is what the rule is
        # compared in. The final arm rather than a `CURRENCY_SUBJECTS` test: a
        # subject that is neither a proportion nor a count nor a price is money
        # by elimination, and testing for it leaves an unreachable `else`.
        amount = f"{format_value(rule.threshold)} {currency}"

    return f"{subject_phrase(rule)} " f"{rule.get_direction_display().lower()} {amount}"

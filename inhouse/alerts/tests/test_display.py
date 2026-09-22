"""Testing module for :py:mod:`widgets.inhouse.alerts.display` module."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from widgets.inhouse.alerts.display import (
    describe,
    format_percent,
    format_price,
    format_value,
    page_label,
)
from widgets.inhouse.alerts.models import AlertRule, Direction, Subject

ADDRESS = "2EVGZ4BGOSL3J64UYDE2BUGTNTBZZZLI54VUQQNZZLYCDODLY33UGXNSIU"
OTHER = "7XBGHMVIQE6HC3RUFAB7NPPGWFQNJ4KMHGMLDLMBWAQHJ6GTSYPPQJGY3Q"
BUNDLE = "86C2B129E807A583C4D37BA182B4EC26F64B3CC9"


@pytest.fixture
def reader(db):
    """A user to hang rules on."""
    return get_user_model().objects.create_user(
        username="display@example.com", email="display@example.com", password="x"
    )


def _rule(reader, **overrides):
    """Store one rule."""
    fields = {
        "user": reader,
        "subject": Subject.TOTAL_VALUE,
        "direction": Direction.DOWN,
        "threshold": "100",
        "address": BUNDLE,
    }
    fields.update(overrides)
    return AlertRule.objects.create(**fields)


def _resolves(mocker, addresses):
    """Patch the host's resolver to answer `addresses`."""
    return mocker.patch(
        "api.widgets.bundle_and_addresses_from_path",
        return_value=(BUNDLE, addresses),
    )


class TestAlertsDisplayNumbers:
    """Testing class for how a threshold is written out.

    **The column's scale is not a presentation.** `threshold` is
    `decimal_places=10`, so every rule read "falls below 100.0000000000" - which
    is the database describing itself to somebody who typed "100".
    """

    @pytest.mark.parametrize(
        ("amount", "expected"),
        [(Decimal("100"), "100.00"), (Decimal("2.5"), "2.50"), (0, "0.00")],
    )
    def test_alerts_display_a_value_keeps_two_places(self, amount, expected):
        """Trailing zeros kept, because money reads that way - "100" for a
        portfolio total looks like a count of something."""
        assert format_value(amount) == expected

    @pytest.mark.parametrize(
        ("amount", "expected"),
        [
            (Decimal("124.456"), "124.456"),
            (Decimal("1.5"), "1.5"),
            (Decimal("0.1234567"), "0.123457"),
        ],
    )
    def test_alerts_display_a_price_drops_trailing_zeros(self, amount, expected):
        assert format_price(amount) == expected

    def test_alerts_display_a_small_price_is_not_rounded_to_nothing(self):
        """**The most misleading thing this could print is "0".**

        An ASA price below a millionth of an ALGO is ordinary. Rendered at two
        places, or at six, it becomes a threshold the reader never chose and
        reads as an asset worth nothing.
        """
        assert format_price(Decimal("0.0000000123")) == "0.0000000123"

    def test_alerts_display_a_price_claims_no_more_than_is_stored(self):
        """Ten places is the column's own scale, so nothing below it exists to
        be shown - printing further would be inventing precision."""
        assert format_price(Decimal("0.00000000001")) == "0"

    def test_alerts_display_a_zero_price_is_zero(self):
        assert format_price(Decimal("0")) == "0"

    @pytest.mark.parametrize(
        "amount",
        ["", "NaN", None, object(), Decimal("NaN"), Decimal("Infinity")],
    )
    def test_alerts_display_a_figure_that_is_not_one_is_zero(self, amount):
        """**This renders a panel and builds a notification**, and neither has
        anywhere to put a `decimal.InvalidOperation`. Nothing should ever reach
        here - `threshold` is a `DecimalField` - so the cost of being wrong
        about that is a figure that reads "0.00" rather than a page that 500s.

        `NaN` and `Infinity` are in the list because they are *valid* Decimals:
        they survive parsing and then format as themselves, so a notification
        would read "NaN ALGO" - which says the site is broken rather than
        naming a figure to check.
        """
        assert format_value(amount) == "0.00"

    @pytest.mark.parametrize(
        ("amount", "expected"),
        [(Decimal("5"), "5%"), (Decimal("2.50"), "2.5%"), (Decimal("0.25"), "0.25%")],
    )
    def test_alerts_display_a_percentage_is_written_as_one(self, amount, expected):
        assert format_percent(amount) == expected


@pytest.mark.django_db
class TestAlertsDisplayPageLabel:
    """Testing class for naming the page a rule watches."""

    def test_alerts_display_a_single_address_bundle_shows_the_address(
        self, mocker
    ):
        """**Every page is a bundle, including one address.**

        A reader who set a rule on their own address was told about
        `86C2B129…`, a hash of the address they were looking at. One address in
        the bundle means that is what they meant.
        """
        _resolves(mocker, ADDRESS)

        assert page_label(BUNDLE) == ADDRESS[:5] + "..." + ADDRESS[-5:]

    def test_alerts_display_a_real_bundle_stays_a_bundle(self, mocker):
        """Several addresses have no single name, so the page keeps its own."""
        _resolves(mocker, f"{ADDRESS} {OTHER}")

        assert page_label(BUNDLE) == BUNDLE[:5] + "..." + BUNDLE[-5:]

    def test_alerts_display_an_unresolvable_bundle_shows_itself(self, mocker):
        """A cache miss is not a reason to render nothing - the hash is still
        what the rule watches, and is still the thing to quote in a report."""
        _resolves(mocker, "")

        assert page_label(BUNDLE) == BUNDLE[:5] + "..." + BUNDLE[-5:]

    def test_alerts_display_a_resolver_that_raises_does_not(self, mocker):
        """This runs while rendering a panel and while building a
        notification, and neither has anywhere to put an exception."""
        mocker.patch(
            "api.widgets.bundle_and_addresses_from_path",
            side_effect=RuntimeError("redis is away"),
        )

        assert page_label(BUNDLE) == BUNDLE[:5] + "..." + BUNDLE[-5:]

    def test_alerts_display_an_empty_page_is_empty(self):
        """Asset subjects carry no address, and nothing must be invented."""
        assert page_label("") == ""


@pytest.mark.django_db
class TestAlertsDisplayDescribe:
    """Testing class for the sentence a reader is shown.

    One function, because the panel's list and the notification body must say
    the same words - a reader who agreed to one and received the other has no
    way to connect them.
    """

    def test_alerts_display_describes_a_total(self, reader, mocker):
        _resolves(mocker, ADDRESS)

        assert describe(_rule(reader)) == (
            f"Portfolio total {ADDRESS[:5]}...{ADDRESS[-5:]} "
            "falls below 100.00 ALGO"
        )

    def test_alerts_display_describes_a_price(self, reader, mocker):
        rule = _rule(
            reader,
            subject=Subject.ASA_PRICE,
            asset_id=31566704,
            threshold="0.1234",
            direction=Direction.UP,
        )

        assert describe(rule) == "Asset price 31566704 rises above 0.1234 ALGO"

    def test_alerts_display_describes_a_percentage(self, reader, mocker):
        _resolves(mocker, ADDRESS)
        rule = _rule(
            reader,
            subject=Subject.TOTAL_PERCENT,
            threshold="5",
            window_seconds=3600,
        )

        assert describe(rule).endswith("falls below 5%")

    def test_alerts_display_an_asset_rule_needs_no_resolver(self, reader, mocker):
        """An asset subject names an asset, so there is no page to resolve -
        and a cache read per row for a value that is not used would be the kind
        of cost that hides behind a template tag."""
        resolver = _resolves(mocker, ADDRESS)
        describe(_rule(reader, subject=Subject.ASA_TOTAL, asset_id=31566704))

        assert resolver.called is False

    def test_alerts_display_a_holding_is_a_value_not_a_price(self, reader):
        """`asa_total` is what the reader holds, in ALGO, so it reads like a
        total rather than like a price."""
        rule = _rule(reader, subject=Subject.ASA_TOTAL, asset_id=1, threshold="7")

        assert describe(rule).endswith("falls below 7.00 ALGO")

"""Testing module for :py:mod:`widgets.inhouse.alerts.display` module."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from widgets.inhouse.alerts.display import (
    asset_label,
    describe,
    disclosure,
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
    if overrides.get("subject") in {Subject.ASA_AMOUNT}:
        fields["direction"] = Direction.UP
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
            f"Portfolio total for {ADDRESS[:5]}...{ADDRESS[-5:]} "
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

        assert describe(rule) == "#31566704 price rises above 0.1234 ALGO"

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


class TestAlertsDisplayDisclosure:
    """Testing class for telling a reader what a price is worth trusting.

    **The decision this implements**, taken 2026-09-22: disclose rather than
    refuse or suppress. A price from shallow pools moves several percent on one
    swap and back, so a rule watching it fires on noise that reads exactly like
    news - and the alternatives both make us pick a liquidity threshold on the
    reader's behalf, with a rule that stops firing and never says why.
    """

    def test_alerts_display_discloses_the_depth_in_algo(self):
        """ALGO, because "pools hold 4,000,000 units" says nothing without
        knowing what a unit is worth."""
        assert disclosure(340.0) == "pools hold ~340.00 ALGO"

    def test_alerts_display_says_nothing_about_an_unknown_depth(self):
        """**A missing measurement is not a small one.**

        The engine sends no depth for an asset it could not price, and an older
        engine sends none at all. Printing "0 ALGO" there would read as a
        finding - the worst possible one, since a reader would take it as
        proof the asset is untradeable.
        """
        assert disclosure(None) == ""

    def test_alerts_display_says_nothing_about_a_zero_depth(self):
        assert disclosure(0) == ""

    def test_alerts_display_discloses_a_deep_pool_too(self):
        """**Said either way, which is what makes it threshold-free.** For a
        deep asset the figure reassures; for a thin one it warns. Choosing when
        to speak would be choosing the threshold we decided not to pick."""
        assert disclosure(1_250_000.0) == "pools hold ~1250000.00 ALGO"


@pytest.mark.django_db
class TestAlertsDisplayTheAssetAndItsCurrency:
    """Testing class for naming the asset and the reader's own currency."""

    def test_alerts_display_names_the_asset_by_its_unit(self, reader):
        """**"an asset 31566704" is not what a reader recognises.** They chose
        "USDC" out of a picker that showed them that word, so that is what the
        notification says."""
        rule = _rule(
            reader,
            subject=Subject.ASA_TOTAL,
            asset_id=31566704,
            asset_unit="USDC",
        )

        assert asset_label(rule) == "USDC"
        assert describe(rule).startswith("My USDC holding's value")

    def test_alerts_display_falls_back_to_the_id(self, reader):
        """A rule written before the unit was stored still has to describe
        itself - and a client that sends no unit must not produce a blank."""
        rule = _rule(reader, subject=Subject.ASA_TOTAL, asset_id=31566704)

        assert asset_label(rule) == "#31566704"

    def test_alerts_display_ignores_a_blank_unit(self, reader):
        rule = _rule(
            reader, subject=Subject.ASA_TOTAL, asset_id=31566704, asset_unit="  "
        )

        assert asset_label(rule) == "#31566704"

    def test_alerts_display_names_a_usd_threshold_in_usd(self, reader, mocker):
        """**The reader's own currency**, because that is what it is compared
        in now. It used to be converted to ALGO at creation and shown back as
        an ALGO figure they never typed."""
        _resolves(mocker, ADDRESS)
        rule = _rule(reader, threshold_unit="usd")

        assert describe(rule).endswith("falls below 100.00 USD")

    def test_alerts_display_names_a_usd_price_in_usd(self, reader):
        rule = _rule(
            reader,
            subject=Subject.ASA_PRICE,
            asset_id=1,
            threshold="0.5",
            threshold_unit="usd",
        )

        assert describe(rule).endswith("falls below 0.5 USD")

    def test_alerts_display_describes_an_amount_in_the_assets_own_units(
        self, reader
    ):
        """**No currency at all.** A count of the asset is not money, so the
        figure is followed by the asset rather than by ALGO or USD."""
        rule = _rule(
            reader,
            subject=Subject.ASA_AMOUNT,
            asset_id=31566704,
            asset_unit="ASASTATS",
            threshold="1000",
        )

        assert describe(rule) == "My ASASTATS holding rises above 1,000"

    def test_alerts_display_reads_as_a_sentence_for_every_subject(self, reader, mocker):
        """**The reported bug, pinned for all six.**

        The subject came from `get_subject_display()`, which is a *picker
        option* - it answers "what do you want to watch?" and reads "How much
        of an asset I hold". In front of an asset it produced "How much of an
        asset I hold 393537671 rises above 1000000 393537671": the option's own
        wording, the asset named where the option already said "an asset", and
        the asset a second time because the count carried it as a unit.

        Asserted whole rather than by fragment, because what was wrong with it
        was the shape of the whole line.
        """
        _resolves(mocker, ADDRESS)
        page = f"{ADDRESS[:5]}...{ADDRESS[-5:]}"
        cases = {
            Subject.ASA_PRICE: "HOG price rises above 1,000",
            Subject.ASA_PRICE_PERCENT: "HOG price change rises above 1000%",
            Subject.ASA_AMOUNT: "My HOG holding rises above 1,000",
            Subject.ASA_TOTAL: "My HOG holding's value rises above 1000.00 ALGO",
            Subject.TOTAL_VALUE: (
                f"Portfolio total for {page} rises above 1000.00 ALGO"
            ),
            Subject.TOTAL_PERCENT: (
                f"Portfolio total change for {page} rises above 1000%"
            ),
        }
        for subject, expected in cases.items():
            rule = _rule(
                reader,
                subject=subject,
                asset_id=7,
                asset_unit="HOG",
                threshold="1000",
                direction=Direction.UP,
                window_seconds=3600,
            )
            # The price subject is the one that is not grouped: a price is
            # small by nature, and "1,000" would be a strange threshold to
            # read against a figure rendered "0.005".
            if subject == Subject.ASA_PRICE:
                expected = "HOG price rises above 1000 ALGO"

            assert describe(rule) == expected, subject

    def test_alerts_display_never_names_the_asset_twice(self, reader):
        """A count used to carry the asset as its unit while the subject named
        it too. The subject names it; the figure does not repeat it."""
        rule = _rule(
            reader,
            subject=Subject.ASA_AMOUNT,
            asset_id=7,
            asset_unit="HOG",
            threshold="1000",
        )

        assert describe(rule).count("HOG") == 1

    def test_alerts_display_groups_a_long_count(self, reader):
        """**A million of a token is the figure that gets long here.**
        "1000000" is digits to be counted; "1,000,000" is a number to be read.
        Values and prices stay ungrouped - a price is small by nature and the
        rest of the site renders money ungrouped."""
        rule = _rule(
            reader,
            subject=Subject.ASA_AMOUNT,
            asset_id=7,
            asset_unit="HOG",
            threshold="1000000",
        )

        assert describe(rule) == "My HOG holding rises above 1,000,000"

    @pytest.mark.parametrize(
        "threshold",
        ["0", "-1000000", "1E+30", "1e-30", "NaN", "Infinity", "-Infinity", "abc"],
    )
    def test_alerts_display_groups_whatever_a_threshold_turns_out_to_be(
        self, threshold
    ):
        """**The invariant that makes a guard unnecessary, asserted directly.**

        `format_count` groups the whole part with `int()`, unguarded: `_number`
        answers a finite Decimal for every one of these - including the ones
        that are not numbers at all - and `_trimmed` renders it with `:.6f`,
        which never produces an exponent. A `try` around it was dead code, and
        the only test that could have covered it would have had to fake an
        input production cannot produce.

        **Unsaved, and that is the point.** The column refuses five of these,
        so a stored rule can never hold them - but the instance a form just
        saved still carries the *string that was posted*, and that is the
        instance the panel re-renders and the notification is built from. It is
        the one path on which a threshold is not yet a Decimal, which is what
        `_number` exists for.
        """
        rule = AlertRule(
            subject=Subject.ASA_AMOUNT,
            direction=Direction.UP,
            asset_id=7,
            asset_unit="HOG",
            threshold=threshold,
            address=BUNDLE,
        )

        sentence = describe(rule)

        assert sentence.startswith("My HOG holding ")
        assert "NaN" not in sentence
        assert "Infinity" not in sentence

    def test_alerts_display_keeps_a_fractional_count(self, reader):
        """Grouping the whole part must not eat the rest of the number."""
        rule = _rule(
            reader,
            subject=Subject.ASA_AMOUNT,
            asset_id=7,
            asset_unit="HOG",
            threshold="1234567.25",
        )

        assert describe(rule).endswith("1,234,567.25")

    def test_alerts_display_describes_an_amount_with_no_unit_stored(self, reader):
        rule = _rule(
            reader, subject=Subject.ASA_AMOUNT, asset_id=7, threshold="1000"
        )

        assert describe(rule) == "My #7 holding rises above 1,000"

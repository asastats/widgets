"""Testing module for :py:mod:`widgets.inhouse.alerts.evaluate` module."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from widgets.inhouse.alerts.evaluate import (
    SKIPPED,
    cooling_down,
    evaluate_page,
    evaluate_prices,
    payload_for,
    reading_for,
)
from widgets.inhouse.alerts.models import AlertRule, Direction, Subject

PAGE = "BUNDLEHASH"


@pytest.fixture
def reader(db):
    """Return a user to hang rules on."""
    return get_user_model().objects.create_user(
        username="eval@example.com", email="eval@example.com", password="x"
    )


def _rule(reader, **overrides):
    """Store one rule on PAGE."""
    fields = {
        "user": reader,
        "subject": Subject.TOTAL_VALUE,
        "direction": Direction.DOWN,
        "threshold": "100",
        "address": PAGE,
    }
    fields.update(overrides)
    return AlertRule.objects.create(**fields)


class TestAlertsEvaluateReading:
    """Testing class for what a rule reads from a payload."""

    def test_alerts_evaluate_a_total_rule_reads_the_total(self, db, reader):
        rule = _rule(reader, subject=Subject.TOTAL_VALUE)

        assert reading_for(rule, 120.5, {}) == 120.5

    def test_alerts_evaluate_an_asset_rule_reads_its_asset(self, db, reader):
        rule = _rule(reader, subject=Subject.ASA_TOTAL, asset_id=31566704)

        assert reading_for(rule, 120.5, {31566704: 7.25}) == 7.25

    def test_alerts_evaluate_a_missing_asset_is_not_a_zero(self, db, reader):
        """**The difference that would fire every "falls below" rule.**

        The pass publishes the holdings it priced. An asset absent from this
        block was not re-priced, which is not the same as being worth nothing -
        reading it as zero would report a collapse to everybody holding it.
        """
        rule = _rule(reader, subject=Subject.ASA_TOTAL, asset_id=31566704)

        assert reading_for(rule, 120.5, {999: 1.0}) is None

    @pytest.mark.parametrize("subject", list(SKIPPED))
    def test_alerts_evaluate_skipped_subjects_have_no_reading(
        self, db, reader, subject
    ):
        rule = _rule(reader, subject=subject)

        assert reading_for(rule, 120.5, {1: 2.0}) is None


class TestAlertsEvaluateCooldown:
    """Testing class for staying quiet after firing."""

    def test_alerts_evaluate_a_rule_that_never_fired_is_not_cooling(
        self, db, reader
    ):
        assert cooling_down(_rule(reader), timezone.now()) is False

    def test_alerts_evaluate_a_rule_that_just_fired_is_cooling(self, db, reader):
        now = timezone.now()
        rule = _rule(reader, last_fired_at=now - timedelta(seconds=60))

        assert cooling_down(rule, now) is True

    def test_alerts_evaluate_a_rule_past_its_cooldown_is_not(self, db, reader):
        now = timezone.now()
        rule = _rule(reader, last_fired_at=now - timedelta(seconds=1000))

        assert cooling_down(rule, now) is False


@pytest.mark.django_db
class TestAlertsEvaluatePage:
    """Testing class for evaluating a whole page."""

    def test_alerts_evaluate_reports_a_crossing(self, reader):
        _rule(reader, last_value="120")

        fired, skipped = evaluate_page(PAGE, {"total": 90})

        assert len(fired) == 1
        assert skipped == 0

    def test_alerts_evaluate_is_silent_while_it_stays_past_the_line(self, reader):
        """The tick after the one that fired, which is the whole reason a
        crossing is used rather than a level."""
        _rule(reader, last_value="90")

        fired, _ = evaluate_page(PAGE, {"total": 80})

        assert fired == []

    def test_alerts_evaluate_records_the_reading_even_when_silent(self, reader):
        """**Every rule's `last_value` advances, fired or not.** A skipped
        update leaves the rule comparing against something older than the last
        block, and a value that crossed and came back would be reported the next
        time anything moved."""
        rule = _rule(reader, last_value="120")

        evaluate_page(PAGE, {"total": 110})

        rule.refresh_from_db()
        assert float(rule.last_value) == 110

    def test_alerts_evaluate_arms_a_rule_that_has_seen_nothing(self, reader):
        """A first reading past the threshold is not a crossing the reader was
        there for."""
        rule = _rule(reader, last_value=None)

        fired, _ = evaluate_page(PAGE, {"total": 10})

        assert fired == []
        rule.refresh_from_db()
        assert float(rule.last_value) == 10

    def test_alerts_evaluate_respects_the_cooldown(self, reader):
        now = timezone.now()
        _rule(
            reader, last_value="120", last_fired_at=now - timedelta(seconds=60)
        )

        fired, _ = evaluate_page(PAGE, {"total": 90}, now=now)

        assert fired == []

    def test_alerts_evaluate_does_not_push_the_cooldown_further_out(
        self, reader
    ):
        """**Checked before firing, not after.** Advancing `last_fired_at` on a
        suppressed crossing would move the next legitimate alert further away
        every time the value wobbled."""
        now = timezone.now()
        fired_at = now - timedelta(seconds=60)
        rule = _rule(reader, last_value="120", last_fired_at=fired_at)

        evaluate_page(PAGE, {"total": 90}, now=now)

        rule.refresh_from_db()
        assert rule.last_fired_at == fired_at

    def test_alerts_evaluate_counts_what_it_cannot_answer(self, reader):
        """**Skipped loudly.** A rule that is stored, looks active and can never
        fire is the worst thing this could produce silently."""
        _rule(reader, subject=Subject.TOTAL_PERCENT, window_seconds=3600)
        _rule(reader, subject=Subject.ASA_PRICE, asset_id=1)

        fired, skipped = evaluate_page(PAGE, {"total": 90})

        assert (fired, skipped) == ([], 2)

    def test_alerts_evaluate_leaves_another_pages_rules_alone(self, reader):
        other = _rule(reader, address="OTHERPAGE", last_value="120")

        evaluate_page(PAGE, {"total": 90})

        other.refresh_from_db()
        assert float(other.last_value) == 120

    def test_alerts_evaluate_ignores_an_inactive_rule(self, reader):
        _rule(reader, last_value="120", active=False)

        fired, _ = evaluate_page(PAGE, {"total": 90})

        assert fired == []

    def test_alerts_evaluate_survives_an_empty_payload(self, reader):
        _rule(reader, last_value="120")

        assert evaluate_page(PAGE, None) == ([], 0)

    def test_alerts_evaluate_an_upward_rule_fires_upward(self, reader):
        _rule(reader, direction=Direction.UP, last_value="90")

        fired, _ = evaluate_page(PAGE, {"total": 110})

        assert len(fired) == 1


@pytest.mark.django_db
class TestAlertsEvaluatePayloadFor:
    """Testing class for reading what the pass published."""

    def test_alerts_evaluate_decodes_a_published_payload(self, mocker):
        import msgpack

        client = mocker.MagicMock()
        client.get.return_value = msgpack.packb(
            {"total": 5.0, "values": {31566704: 1.5}}
        )

        payload = payload_for(PAGE, client)

        assert payload["total"] == 5.0
        # Integer keys, which is how the fragments address them and how
        # `reading_for` looks one up. A str key here would never match.
        assert payload["values"][31566704] == 1.5

    def test_alerts_evaluate_returns_none_when_nothing_is_published(
        self, mocker
    ):
        client = mocker.MagicMock()
        client.get.return_value = None

        assert payload_for(PAGE, client) is None

    def test_alerts_evaluate_survives_a_redis_that_is_away(self, mocker):
        client = mocker.MagicMock()
        client.get.side_effect = OSError("no route to host")

        assert payload_for(PAGE, client) is None

    def test_alerts_evaluate_makes_its_own_client_when_given_none(self, mocker):
        instance = mocker.patch("utils.clients.redis_instance")
        instance.return_value.get.return_value = None

        payload_for(PAGE)

        assert instance.called


@pytest.mark.django_db
class TestAlertsEvaluatePrices:
    """Testing class for the per-asset evaluator."""

    def _price_rule(self, reader, **overrides):
        fields = {
            "user": reader,
            "subject": Subject.ASA_PRICE,
            "direction": Direction.DOWN,
            "threshold": "1",
            "asset_id": 31566704,
        }
        fields.update(overrides)
        return AlertRule.objects.create(**fields)

    def test_alerts_evaluate_prices_reports_a_crossing(self, reader):
        self._price_rule(reader, last_value="2")

        fired = evaluate_prices({31566704: 0.5})

        assert len(fired) == 1

    def test_alerts_evaluate_prices_is_silent_while_it_stays_past(self, reader):
        self._price_rule(reader, last_value="0.5")

        assert evaluate_prices({31566704: 0.4}) == []

    def test_alerts_evaluate_prices_arms_a_rule_that_has_seen_nothing(self, reader):
        """A first reading past the threshold is not a crossing the reader was
        there for - the same rule the page evaluator applies."""
        rule = self._price_rule(reader, last_value=None)

        assert evaluate_prices({31566704: 0.5}) == []
        rule.refresh_from_db()
        assert float(rule.last_value) == 0.5

    def test_alerts_evaluate_prices_records_the_reading_when_silent(self, reader):
        rule = self._price_rule(reader, last_value="2")

        evaluate_prices({31566704: 1.5})

        rule.refresh_from_db()
        assert float(rule.last_value) == 1.5

    def test_alerts_evaluate_prices_respects_the_cooldown(self, reader):
        now = timezone.now()
        self._price_rule(
            reader, last_value="2", last_fired_at=now - timedelta(seconds=60)
        )

        assert evaluate_prices({31566704: 0.5}, now=now) == []

    def test_alerts_evaluate_prices_a_price_it_could_not_compute_is_not_zero(
        self, reader
    ):
        """**The asset most likely to have rules on it is the one in trouble.**

        An asset whose pools have gone prices at nothing. Reading that None as a
        collapse to zero would fire every "falls below" rule naming it at once,
        on an asset that may simply have been delisted from one venue.
        """
        rule = self._price_rule(reader, last_value="2")

        assert evaluate_prices({31566704: None}) == []
        rule.refresh_from_db()
        assert float(rule.last_value) == 2, "and it keeps what it last saw"

    def test_alerts_evaluate_prices_ignores_an_unwatched_asset(self, reader):
        self._price_rule(reader, last_value="2")

        assert evaluate_prices({999: 0.5}) == []

    def test_alerts_evaluate_prices_ignores_a_holding_rule(self, reader):
        """`asa_total` names an asset too and is answered by the page
        evaluator. Evaluating it here would compare a *price* against a
        threshold the reader set on their holding's value."""
        self._price_rule(reader, subject=Subject.ASA_TOTAL, last_value="2")

        assert evaluate_prices({31566704: 0.5}) == []

    def test_alerts_evaluate_prices_ignores_an_inactive_rule(self, reader):
        self._price_rule(reader, last_value="2", active=False)

        assert evaluate_prices({31566704: 0.5}) == []

    def test_alerts_evaluate_prices_survives_an_empty_body(self, reader):
        self._price_rule(reader, last_value="2")

        assert evaluate_prices({}) == []
        assert evaluate_prices(None) == []

    def test_alerts_evaluate_prices_fires_upward_too(self, reader):
        self._price_rule(reader, direction=Direction.UP, last_value="0.5")

        assert len(evaluate_prices({31566704: 2.0})) == 1

    def test_alerts_evaluate_prices_asks_once_per_asset(self, reader, django_assert_num_queries):
        """**One question per asset, however many readers ask it.** Two rules on
        one asset must not be two queries - that is what the `asset_id, active`
        index on the model is for."""
        self._price_rule(reader, last_value="2")
        self._price_rule(reader, last_value="2", threshold="1.5")

        with django_assert_num_queries(3):  # one select, two saves
            evaluate_prices({31566704: 0.5})

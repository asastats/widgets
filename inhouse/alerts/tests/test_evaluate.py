"""Testing module for :py:mod:`widgets.inhouse.alerts.evaluate` module."""

import logging
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from widgets.inhouse.alerts.evaluate import (
    SKIPPED,
    cooling_down,
    evaluate_page,
    evaluate_prices,
    percent_move,
    payload_for,
    reading_for,
)
from widgets.inhouse.alerts.models import (
    AlertRule,
    Direction,
    PushSubscription,
    Subject,
)

PAGE = "BUNDLEHASH"


@pytest.fixture
def reader(db):
    """Return a user to hang rules on, with a browser to notify.

    **The subscription is not incidental.** A rule whose reader has no browser
    is *held* rather than evaluated - see `_with_delivery` - so a fixture
    without one would make every test here assert that nothing fires, which is
    true and useless. The held case has its own class below.
    """
    user = get_user_model().objects.create_user(
        username="eval@example.com", email="eval@example.com", password="x"
    )
    PushSubscription.objects.create(
        user=user,
        endpoint="https://push.example/eval",
        p256dh="p",
        auth="a",
    )
    return user


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
        fire is the worst thing this could produce silently.

        Only `asa_price` now: it is answered by the periodic task rather than
        here, so being counted means "handled elsewhere" and not "dropped".
        """
        _rule(reader, subject=Subject.ASA_PRICE, asset_id=1)

        fired, skipped = evaluate_page(PAGE, {"total": 90})

        assert (fired, skipped) == ([], 1)

    def test_alerts_evaluate_no_longer_skips_a_percentage_rule(self, reader, mocker):
        """It is read rather than counted now - the history answers it."""
        client = mocker.MagicMock()
        client.zrevrangebyscore.return_value = []
        _rule(reader, subject=Subject.TOTAL_PERCENT, window_seconds=3600)

        fired, skipped = evaluate_page(PAGE, {"total": 90}, client=client)

        assert (fired, skipped) == ([], 0)
        assert client.zrevrangebyscore.called

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


@pytest.mark.django_db
class TestAlertsEvaluatePricesHeld:
    """Testing class for a price rule whose reader has no browser on.

    **Held, not spent.** Firing it would advance `last_value` past the
    threshold, so the next evaluation would see no crossing - the alert would be
    gone rather than waiting, and the modal promises three times over that rules
    saved now will be there when a browser is turned on.
    """

    @pytest.fixture
    def silent(self, db):
        """A reader with rules and no subscription."""
        return get_user_model().objects.create_user(
            username="silent@example.com",
            email="silent@example.com",
            password="x",
        )

    def _price_rule(self, user, **overrides):
        fields = {
            "user": user,
            "subject": Subject.ASA_PRICE,
            "direction": Direction.DOWN,
            "threshold": "1",
            "asset_id": 31566704,
            "last_value": "2",
        }
        fields.update(overrides)
        return AlertRule.objects.create(**fields)

    def test_alerts_evaluate_prices_holds_a_rule_with_nowhere_to_go(self, silent):
        rule = self._price_rule(silent)

        assert evaluate_prices({31566704: 0.5}) == []
        rule.refresh_from_db()
        assert float(rule.last_value) == 2, "the crossing must still be waiting"
        assert rule.last_fired_at is None

    def test_alerts_evaluate_prices_says_how_many_were_held(self, silent, caplog):
        """**"My alert never fired" is the question this answers.** Held rules
        are counted and logged rather than skipped quietly, so the log can tell
        "nobody was listening" from "it never crossed"."""
        self._price_rule(silent)
        self._price_rule(silent, asset_id=386192725)

        with caplog.at_level(logging.INFO):
            evaluate_prices({31566704: 0.5, 386192725: 0.5})

        assert "2 price rule(s) held" in caplog.text

    def test_alerts_evaluate_prices_still_answers_a_reader_who_can_hear(
        self, silent, reader
    ):
        """One held rule must not cost another reader their notification."""
        self._price_rule(silent)
        self._price_rule(reader)

        assert len(evaluate_prices({31566704: 0.5})) == 1


@pytest.mark.django_db
class TestAlertsEvaluatePricePercent:
    """Testing class for the percentage half of the per-asset evaluator."""

    def _rule(self, reader, **overrides):
        fields = {
            "user": reader,
            "subject": Subject.ASA_PRICE_PERCENT,
            "direction": Direction.DOWN,
            "threshold": "5",
            "asset_id": 31566704,
            "window_seconds": 3600,
        }
        fields.update(overrides)
        return AlertRule.objects.create(**fields)

    def _client(self, mocker, members):
        client = mocker.MagicMock()
        client.zrevrangebyscore.return_value = members
        return client

    def test_alerts_evaluate_price_percent_reports_a_crossing(self, reader, mocker):
        """A tenth off the hour's price crosses a "down 5%" rule.

        `last_value` is the move *last* time, not the price: the reading this
        subject compares is a percentage, and the rule was sitting at a move of
        minus one.
        """
        client = self._client(mocker, [b"1000:1.0"])
        self._rule(reader, last_value="-1")

        fired = evaluate_prices({31566704: 0.9}, client=client)

        assert len(fired) == 1

    def test_alerts_evaluate_price_percent_refuses_a_short_history(
        self, reader, mocker
    ):
        """**The reading is refused, and the rule is left armed.**

        No point at or before the far edge means the series does not reach back
        a window - so there is no honest answer, and reporting the move since
        whenever the price task started would be a move over a period the reader
        did not choose. `last_value` must survive that, or the rule would be
        re-armed against a number it never saw.
        """
        client = self._client(mocker, [])
        rule = self._rule(reader, last_value="-1")

        assert evaluate_prices({31566704: 0.5}, client=client) == []
        rule.refresh_from_db()
        assert float(rule.last_value) == -1

    def test_alerts_evaluate_price_percent_reads_its_own_asset(
        self, reader, mocker
    ):
        client = self._client(mocker, [b"1000:1.0"])
        self._rule(reader, asset_id=386192725, last_value="-1")

        evaluate_prices({386192725: 0.9}, client=client, unix_now=10_000)

        assert client.zrevrangebyscore.call_args[0][0] == "lvah:386192725"

    def test_alerts_evaluate_price_percent_does_not_read_for_a_level_rule(
        self, reader, mocker
    ):
        """`asa_price` is answered by the price in the body and nothing else.

        The two subjects ride the same task and the same query; only the
        percentage one costs a read, and a level rule paying for one would be a
        round trip per asset per run for a number it does not use.
        """
        client = self._client(mocker, [b"1000:1.0"])
        AlertRule.objects.create(
            user=reader,
            subject=Subject.ASA_PRICE,
            direction=Direction.DOWN,
            threshold="1",
            asset_id=31566704,
            last_value="2",
        )

        evaluate_prices({31566704: 0.5}, client=client)

        assert client.zrevrangebyscore.called is False


@pytest.mark.django_db
class TestAlertsEvaluatePercentMove:
    """Testing class for reading a move out of the engine's totals history.

    **The window is the whole subject.** Every other reading here is a number
    published this block; this one is a comparison against a number from an hour
    or a week ago, and getting the "ago" wrong is not visible in the alert the
    reader receives.
    """

    def _client(self, mocker, members):
        client = mocker.MagicMock()
        client.zrevrangebyscore.return_value = members
        return client

    def test_alerts_evaluate_percent_move_computes_the_move(self, mocker):
        client = self._client(mocker, [b"1000:100.0"])

        assert percent_move(PAGE, 3600, 110.0, client=client) == pytest.approx(10.0)

    def test_alerts_evaluate_percent_move_is_signed(self, mocker):
        """A fall is a negative move, which is what `AlertRule.line` compares
        against - the reader's threshold is unsigned and their direction is not.
        """
        client = self._client(mocker, [b"1000:100.0"])

        assert percent_move(PAGE, 3600, 90.0, client=client) == pytest.approx(-10.0)

    def test_alerts_evaluate_percent_move_reads_the_asset_series_by_prefix(
        self, mocker
    ):
        """**One function, two series.** `asa_price_percent` compares an asset's
        price against its own history at `lvah:{asset id}`; the page subject
        compares a total against `lvth:{page}`. Same honesty rule, same read -
        so the key is the only thing that differs, and a second copy of this
        function would be a second place for the far-edge rule to rot.
        """
        client = self._client(mocker, [b"1000:0.5"])

        move = percent_move(
            31566704, 3600, 0.55, client=client, now=10_000, prefix="lvah"
        )

        assert move == pytest.approx(10.0)
        assert client.zrevrangebyscore.call_args[0][0] == "lvah:31566704"

    def test_alerts_evaluate_percent_move_asks_past_the_far_edge(self, mocker):
        """**The read that makes the window mean what it says.** It asks for the
        newest point *at or before* `now - window`, so the comparison is against
        a total from a window ago rather than against the oldest one held.
        """
        client = self._client(mocker, [b"1000:100.0"])

        percent_move(PAGE, 3600, 110.0, client=client, now=10_000)

        args, kwargs = client.zrevrangebyscore.call_args
        assert args[0] == f"lvth:{PAGE}"
        assert args[1] == 10_000 - 3600
        assert args[2] == "-inf"
        assert kwargs == {"start": 0, "num": 1}

    def test_alerts_evaluate_percent_move_refuses_a_history_that_is_too_short(
        self, mocker
    ):
        """**The failure this subject waited for.**

        No point older than the window means the question cannot be answered.
        Answering it from the oldest point held would turn "down 5% in 24 hours"
        into "down 5% since we started watching", and the notification would
        look identical either way.
        """
        client = self._client(mocker, [])

        assert percent_move(PAGE, 86400, 110.0, client=client) is None

    def test_alerts_evaluate_percent_move_needs_a_window(self, mocker):
        client = self._client(mocker, [b"1000:100.0"])

        assert percent_move(PAGE, None, 110.0, client=client) is None
        assert client.zrevrangebyscore.called is False

    def test_alerts_evaluate_percent_move_needs_a_total(self, mocker):
        client = self._client(mocker, [b"1000:100.0"])

        assert percent_move(PAGE, 3600, None, client=client) is None

    def test_alerts_evaluate_percent_move_refuses_to_divide_by_nothing(
        self, mocker
    ):
        """A page that was worth nothing and is worth something has moved by an
        undefined percentage, not by an infinite one."""
        client = self._client(mocker, [b"1000:0.0"])

        assert percent_move(PAGE, 3600, 110.0, client=client) is None

    def test_alerts_evaluate_percent_move_survives_a_redis_that_is_away(
        self, mocker
    ):
        client = mocker.MagicMock()
        client.zrevrangebyscore.side_effect = OSError("no route to host")

        assert percent_move(PAGE, 3600, 110.0, client=client) is None

    def test_alerts_evaluate_percent_move_survives_an_unusable_point(self, mocker):
        client = self._client(mocker, [b"1000:not-a-number"])

        assert percent_move(PAGE, 3600, 110.0, client=client) is None

    def test_alerts_evaluate_percent_move_accepts_a_decoded_member(self, mocker):
        client = self._client(mocker, ["1000:100.0"])

        assert percent_move(PAGE, 3600, 110.0, client=client) == pytest.approx(10.0)

    def test_alerts_evaluate_percent_move_makes_its_own_client(self, mocker):
        instance = mocker.patch("utils.clients.redis_instance")
        instance.return_value.zrevrangebyscore.return_value = []

        percent_move(PAGE, 3600, 110.0)

        assert instance.called


@pytest.mark.django_db
class TestAlertsEvaluatePercentRules:
    """Testing class for percentage rules end to end through `evaluate_page`."""

    def _client(self, mocker, members):
        client = mocker.MagicMock()
        client.zrevrangebyscore.return_value = members
        return client

    def _percent_rule(self, reader, **overrides):
        fields = {
            "subject": Subject.TOTAL_PERCENT,
            "window_seconds": 3600,
            "threshold": "5",
            "direction": Direction.DOWN,
        }
        fields.update(overrides)
        return _rule(reader, **fields)

    def test_alerts_evaluate_a_falling_rule_fires_on_a_fall(self, reader, mocker):
        """**`down 5` means the move crossed *minus* five.** Compared against
        positive five, a falling rule fires whenever the move is below +5%,
        which is to say nearly always and for the wrong reason."""
        self._percent_rule(reader, last_value="0")
        client = self._client(mocker, [b"1000:100.0"])

        fired, _ = evaluate_page(PAGE, {"total": 90.0}, client=client)

        assert len(fired) == 1

    def test_alerts_evaluate_a_falling_rule_ignores_a_small_fall(
        self, reader, mocker
    ):
        self._percent_rule(reader, last_value="0")
        client = self._client(mocker, [b"1000:100.0"])

        fired, _ = evaluate_page(PAGE, {"total": 98.0}, client=client)

        assert fired == []

    def test_alerts_evaluate_a_falling_rule_ignores_a_rise(self, reader, mocker):
        """The sign is the whole distinction: +10% is not a 5% fall."""
        self._percent_rule(reader, last_value="0")
        client = self._client(mocker, [b"1000:100.0"])

        fired, _ = evaluate_page(PAGE, {"total": 110.0}, client=client)

        assert fired == []

    def test_alerts_evaluate_a_rising_rule_fires_on_a_rise(self, reader, mocker):
        self._percent_rule(reader, direction=Direction.UP, last_value="0")
        client = self._client(mocker, [b"1000:100.0"])

        fired, _ = evaluate_page(PAGE, {"total": 110.0}, client=client)

        assert len(fired) == 1

    def test_alerts_evaluate_a_percent_rule_records_its_move(self, reader, mocker):
        rule = self._percent_rule(reader, last_value="0")
        client = self._client(mocker, [b"1000:100.0"])

        evaluate_page(PAGE, {"total": 98.0}, client=client)

        rule.refresh_from_db()
        assert float(rule.last_value) == pytest.approx(-2.0)

    def test_alerts_evaluate_a_percent_rule_is_silent_while_it_stays_past(
        self, reader, mocker
    ):
        """It crossed on an earlier tick and has stayed there; a level test
        would notify on every block for as long as the move held."""
        self._percent_rule(reader, last_value="-6")
        client = self._client(mocker, [b"1000:100.0"])

        fired, _ = evaluate_page(PAGE, {"total": 93.0}, client=client)

        assert fired == []

    def test_alerts_evaluate_a_percent_rule_waits_out_its_window(
        self, reader, mocker
    ):
        """**A 24-hour rule fires nothing for its first 24 hours**, and that is
        the correct behaviour rather than a gap to paper over."""
        rule = self._percent_rule(reader, window_seconds=86400, last_value="0")
        client = self._client(mocker, [])

        fired, skipped = evaluate_page(PAGE, {"total": 10.0}, client=client)

        assert (fired, skipped) == ([], 0)
        rule.refresh_from_db()
        assert float(rule.last_value) == 0, "and it learns nothing from the tick"

"""Testing module for the alert rule store."""

import pytest
from django.contrib.auth import get_user_model

from widgets.inhouse.alerts.models import (
    ASSET_SUBJECTS,
    DEFAULT_COOLDOWN_SECONDS,
    AlertRule,
    Direction,
    PERCENT_SUBJECTS,
    Subject,
)


@pytest.fixture
def reader(db):
    """Return a user to hang rules on."""
    return get_user_model().objects.create_user(
        username="alerts-reader", email="alerts@example.com", password="x"
    )


def _rule(reader, **overrides):
    """Return an unsaved rule with workable defaults."""
    fields = {
        "user": reader,
        "subject": Subject.ASA_PRICE,
        "asset_id": 393537671,
        "direction": Direction.DOWN,
        "threshold": "0.05",
    }
    fields.update(overrides)
    return AlertRule(**fields)


class TestAlertRuleCrossing:
    """Testing class for when a rule fires.

    **A crossing, not a level**, which is the decision that keeps this feature
    from being turned off by the people who asked for it. A rule that fires
    whenever the value is past its threshold notifies on every tick for as long
    as it stays there, and an asset oscillating around one notifies forever.
    """

    def test_alerts_models_a_rule_that_has_seen_nothing_does_not_fire(self, reader):
        """**It arms instead**, and this is the case a level test gets wrong.

        The first reading a rule ever takes may already be past the threshold -
        a reader setting "below 0.05" on an asset trading at 0.04 - and firing
        then reports a crossing that did not happen while they were watching.
        """
        rule = _rule(reader, last_value=None)

        assert rule.crossed("0.01") is False

    def test_alerts_models_a_downward_crossing_fires(self, reader):
        rule = _rule(reader, direction=Direction.DOWN, last_value="0.06")

        assert rule.crossed("0.04") is True

    def test_alerts_models_staying_below_does_not_fire_again(self, reader):
        """The tick after the one that fired. This is the whole point."""
        rule = _rule(reader, direction=Direction.DOWN, last_value="0.04")

        assert rule.crossed("0.03") is False

    def test_alerts_models_an_upward_crossing_fires(self, reader):
        rule = _rule(reader, direction=Direction.UP, last_value="0.04")

        assert rule.crossed("0.06") is True

    def test_alerts_models_the_wrong_direction_does_not_fire(self, reader):
        """A "rises above" rule is silent when the price falls through it."""
        rule = _rule(reader, direction=Direction.UP, last_value="0.06")

        assert rule.crossed("0.04") is False

    def test_alerts_models_touching_the_threshold_is_not_yet_a_crossing(
        self, reader
    ):
        """**The boundary, which decides whether a rule can fire twice.**

        Landing exactly on the threshold counts as "not yet past", so the next
        move decides. Were it counted as past, a value resting on the line would
        fire, then fire again when it finally moved - two notifications for one
        event.
        """
        rule = _rule(reader, direction=Direction.DOWN, last_value="0.06")

        assert rule.crossed("0.05") is False

    def test_alerts_models_a_crossing_from_the_threshold_itself_fires(self, reader):
        rule = _rule(reader, direction=Direction.DOWN, last_value="0.05")

        assert rule.crossed("0.049") is True


class TestAlertRuleShape:
    """Testing class for what each subject requires."""

    @pytest.mark.parametrize(
        "subject", [Subject.ASA_PRICE, Subject.ASA_TOTAL]
    )
    def test_alerts_models_asset_subjects_need_an_asset(self, reader, subject):
        assert _rule(reader, subject=subject).needs_asset is True

    @pytest.mark.parametrize(
        "subject", [Subject.TOTAL_VALUE, Subject.TOTAL_PERCENT]
    )
    def test_alerts_models_portfolio_subjects_need_no_asset(self, reader, subject):
        assert _rule(reader, subject=subject).needs_asset is False

    def test_alerts_models_only_a_percentage_subject_needs_a_window(self, reader):
        """**The window is what separates cheap from expensive.**

        An absolute threshold reads a current price, which `appstransmitter`
        already keeps fresh every block. A percentage needs a series, and a
        series is where the thin-asset problem lives - so which subjects carry a
        window is not a detail.
        """
        assert _rule(reader, subject=Subject.TOTAL_PERCENT).needs_window is True
        assert _rule(reader, subject=Subject.TOTAL_VALUE).needs_window is False
        assert _rule(reader, subject=Subject.ASA_PRICE).needs_window is False

    def test_alerts_models_the_subject_sets_agree_with_the_choices(self):
        """Both sets name real subjects, so a renamed choice cannot leave a set
        pointing at nothing while every `needs_*` quietly answers False."""
        names = {choice.value for choice in Subject}

        assert {s.value for s in ASSET_SUBJECTS} <= names
        assert {s.value for s in PERCENT_SUBJECTS} <= names


class TestAlertRulePersistence:
    """Testing class for the stored shape."""

    def test_alerts_models_a_rule_round_trips(self, reader):
        rule = _rule(reader)
        rule.save()

        stored = AlertRule.objects.get(pk=rule.pk)

        assert stored.user == reader
        assert stored.asset_id == 393537671
        assert stored.active is True
        assert stored.cooldown_seconds == DEFAULT_COOLDOWN_SECONDS
        assert stored.last_fired_at is None

    def test_alerts_models_a_portfolio_rule_stores_no_asset(self, reader):
        """The columns are nullable per subject rather than split across two
        tables, because it is one concept to the reader."""
        rule = _rule(
            reader, subject=Subject.TOTAL_VALUE, asset_id=None, address="BUNDLE"
        )
        rule.save()

        assert AlertRule.objects.get(pk=rule.pk).asset_id is None

    def test_alerts_models_rules_are_reachable_by_asset(self, reader):
        """**The per-asset evaluator's only query.**

        It asks "who cares about this asset" once per asset rather than once per
        rule, and the same answer says which assets must be kept fresh in
        `CACHE_TRANSMITTER_SET`.
        """
        _rule(reader, asset_id=1).save()
        _rule(reader, asset_id=2).save()
        _rule(reader, asset_id=1, active=False).save()

        assert AlertRule.objects.filter(asset_id=1, active=True).count() == 1

    def test_alerts_models_deleting_the_reader_takes_the_rules(self, reader):
        """Rules are the reader's, and an orphan would be evaluated forever with
        nobody to notify."""
        _rule(reader).save()

        reader.delete()

        assert AlertRule.objects.count() == 0

    def test_alerts_models_describe_themselves_readably(self, reader):
        """`__str__` shows in the admin and in any log line that formats a rule,
        which is where somebody debugging one will meet it first."""
        text = str(_rule(reader, direction=Direction.DOWN))

        assert "393537671" in text
        assert "0.05" in text


@pytest.mark.django_db
class TestPushSubscriptionShape:
    """Testing class for the stored browser."""

    def test_alerts_models_a_subscription_describes_itself(self, reader):
        """`__str__` is what the admin and any log line formatting one shows,
        which is where somebody chasing a delivery problem meets it first."""
        from widgets.inhouse.alerts.models import PushSubscription

        subscription = PushSubscription(
            user=reader,
            endpoint="https://fcm.googleapis.com/fcm/send/" + "x" * 60,
            p256dh="p",
            auth="a",
        )

        text = str(subscription)

        assert str(reader) in text
        # Truncated: an endpoint is 150+ characters of opaque token, and a log
        # line that wraps three times is one nobody reads.
        assert "x" * 60 not in text
        assert text.endswith("…")

    def test_alerts_models_a_subscription_renders_for_pywebpush(self, reader):
        """The nested shape the library wants. A flat dict is accepted and then
        fails at encryption, which is a much worse place to find out."""
        from widgets.inhouse.alerts.models import PushSubscription

        subscription = PushSubscription(
            user=reader, endpoint="https://push.example/x", p256dh="p", auth="a"
        )

        assert subscription.as_dict() == {
            "endpoint": "https://push.example/x",
            "keys": {"p256dh": "p", "auth": "a"},
        }

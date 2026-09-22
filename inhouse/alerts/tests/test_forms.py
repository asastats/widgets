"""Testing module for the rule form."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS
from widgets.inhouse.alerts.forms import AlertRuleForm
from widgets.inhouse.alerts.models import AlertRule, Direction, Subject


def _reader(tier="Professional", email="form@example.com"):
    """Return a user whose profile sits at `tier`."""
    user = get_user_model().objects.create_user(
        username=email, email=email, password="x"
    )
    profile = user.profile
    profile.permission = SUBSCRIPTION_TIER_PERMISSIONS[tier]
    profile.save()
    return user


def _post(**overrides):
    """Return a workable POST payload."""
    data = {
        "subject": Subject.ASA_PRICE,
        "direction": Direction.DOWN,
        "threshold": "0.05",
        "asset_id": "393537671",
    }
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not None}


@pytest.mark.django_db
class TestAlertRuleFormShape:
    """Testing class for the per-subject requirements."""

    def test_alerts_forms_an_asset_rule_needs_an_asset(self):
        """Otherwise it is a rule that watches nothing, stored and never
        matching anything the evaluator looks at."""
        form = AlertRuleForm(_post(asset_id=None), user=_reader())

        assert form.is_valid() is False
        assert "asset_id" in form.errors

    def test_alerts_forms_a_portfolio_rule_clears_a_leftover_asset(self):
        """**Cleared rather than rejected.** The modal keeps the field mounted
        while the reader switches subject, so a leftover value is the ordinary
        case - refusing it would be a puzzle rather than a correction."""
        form = AlertRuleForm(
            _post(subject=Subject.TOTAL_VALUE, asset_id="123"),
            user=_reader(),
        )

        assert form.is_valid() is True
        assert form.cleaned_data["asset_id"] is None

    def test_alerts_forms_a_percentage_rule_needs_a_window(self):
        """A percentage without a period means "since we last looked", which is
        not what the label says."""
        form = AlertRuleForm(
            _post(subject=Subject.TOTAL_PERCENT, asset_id=None, threshold="5"),
            user=_reader(),
        )

        assert form.is_valid() is False
        assert "window_seconds" in form.errors

    def test_alerts_forms_a_percentage_rule_takes_an_offered_window(self):
        form = AlertRuleForm(
            _post(
                subject=Subject.TOTAL_PERCENT,
                asset_id=None,
                threshold="5",
                window_seconds="3600",
            ),
            user=_reader(),
        )

        assert form.is_valid() is True, form.errors

    def test_alerts_forms_refuse_a_window_that_was_not_offered(self):
        """**A short list rather than a free number**, because the honest
        period depends on how often the thing is sampled and a reader has no way
        to know that. A posted value outside the list is not a reader's choice.
        """
        form = AlertRuleForm(
            _post(
                subject=Subject.TOTAL_PERCENT,
                asset_id=None,
                threshold="5",
                window_seconds="61",
            ),
            user=_reader(),
        )

        assert form.is_valid() is False

    def test_alerts_forms_refuse_a_percentage_over_a_hundred(self):
        """Falling more than 100% is a threshold nothing can cross."""
        form = AlertRuleForm(
            _post(
                subject=Subject.TOTAL_PERCENT,
                asset_id=None,
                threshold="150",
                window_seconds="3600",
            ),
            user=_reader(),
        )

        assert form.is_valid() is False
        assert "threshold" in form.errors

    def test_alerts_forms_a_non_percentage_threshold_may_exceed_a_hundred(self):
        """A portfolio total of 5,000 ALGO is an ordinary thing to watch for."""
        form = AlertRuleForm(
            _post(subject=Subject.TOTAL_VALUE, asset_id=None, threshold="5000"),
            user=_reader(),
        )

        assert form.is_valid() is True, form.errors

    @pytest.mark.parametrize("bad", ["0", "-1"])
    def test_alerts_forms_refuse_a_threshold_that_cannot_mean_anything(self, bad):
        form = AlertRuleForm(_post(threshold=bad), user=_reader())

        assert form.is_valid() is False
        assert "threshold" in form.errors

    def test_alerts_forms_refuse_a_subject_nobody_offers(self):
        """The select is server-rendered, so anything else was posted by hand."""
        form = AlertRuleForm(_post(subject="whatever_i_like"), user=_reader())

        assert form.is_valid() is False


@pytest.mark.django_db
class TestAlertRuleFormAllowance:
    """Testing class for the tier cap, enforced where the rule is made."""

    def test_alerts_forms_refuse_a_reader_below_the_tier(self):
        form = AlertRuleForm(_post(), user=_reader(tier="Intro"))

        assert form.is_valid() is False

    def test_alerts_forms_refuse_the_rule_past_the_cap(self):
        """**The cap is checked in the form, not the view**, so that the one
        place a rule is created is the one place the allowance is enforced. A
        view counting separately would be a second answer to drift from this.
        """
        reader = _reader(tier="Asastatser")  # five
        for index in range(5):
            AlertRule.objects.create(
                user=reader,
                subject=Subject.ASA_PRICE,
                direction=Direction.DOWN,
                threshold="1",
                asset_id=index,
            )

        form = AlertRuleForm(_post(), user=reader)

        assert form.is_valid() is False
        assert "5" in str(form.errors)

    def test_alerts_forms_an_inactive_rule_does_not_count(self, ):
        """Deactivating is how a reader keeps a rule without spending a slot,
        so counting the inactive ones would make that meaningless."""
        reader = _reader(tier="Asastatser")
        for index in range(5):
            AlertRule.objects.create(
                user=reader,
                subject=Subject.ASA_PRICE,
                direction=Direction.DOWN,
                threshold="1",
                asset_id=index,
                active=False,
            )

        assert AlertRuleForm(_post(), user=reader).is_valid() is True

    def test_alerts_forms_one_readers_rules_do_not_fill_anothers(self):
        _reader(tier="Asastatser", email="a@example.com")
        crowded = _reader(tier="Asastatser", email="b@example.com")
        for index in range(5):
            AlertRule.objects.create(
                user=crowded,
                subject=Subject.ASA_PRICE,
                direction=Direction.DOWN,
                threshold="1",
                asset_id=index,
            )

        other = get_user_model().objects.get(email="a@example.com")

        assert AlertRuleForm(_post(), user=other).is_valid() is True


@pytest.mark.django_db
class TestAlertRuleFormSave:
    """Testing class for what gets stored."""

    def test_alerts_forms_store_the_page_the_rule_was_made_from(self):
        """A portfolio rule is about *a* total, and which one is the page the
        reader was looking at when they wrote it."""
        form = AlertRuleForm(
            _post(subject=Subject.TOTAL_VALUE, asset_id=None, threshold="100"),
            user=_reader(),
            address="BUNDLEHASH",
        )
        assert form.is_valid(), form.errors

        assert form.save().address == "BUNDLEHASH"

    @pytest.mark.parametrize(
        "subject", [Subject.ASA_PRICE, Subject.ASA_PRICE_PERCENT]
    )
    def test_alerts_forms_publish_the_asset_for_a_priced_subject(
        self, mocker, subject
    ):
        """**`lvra` is the only thing that puts an asset in front of the price
        task**, so a stored rule the engine was never told about is a rule that
        cannot fire.

        Both priced subjects. `asa_price_percent` needs it more than
        `asa_price` does: a level rule reads the price out of the webhook body,
        while a percentage rule reads a *series* that exists only because the
        task writes to it. An asset missing from `lvra` leaves `lvah` empty and
        every reading refused, for ever, with nothing in a log to say so.
        """
        publish = mocker.patch("widgets.inhouse.alerts.forms.publish_assets")
        mocker.patch("widgets.inhouse.alerts.forms.publish_page")
        form = AlertRuleForm(
            _post(subject=subject, threshold="5", window_seconds="3600"),
            user=_reader(),
            address="BUNDLEHASH",
        )
        assert form.is_valid(), form.errors

        form.save()

        publish.assert_called_once_with()

    @pytest.mark.parametrize(
        "subject", [Subject.TOTAL_VALUE, Subject.TOTAL_PERCENT, Subject.ASA_TOTAL]
    )
    def test_alerts_forms_publish_no_asset_for_the_rest(self, mocker, subject):
        """`asa_total` names an asset too and must *not* appear: it is answered
        by the live pass out of what it already published, so publishing it
        would make the price task fetch a price nobody asked for."""
        publish = mocker.patch("widgets.inhouse.alerts.forms.publish_assets")
        mocker.patch("widgets.inhouse.alerts.forms.publish_page")
        form = AlertRuleForm(
            _post(
                subject=subject,
                threshold="5",
                window_seconds="3600",
                asset_id="393537671",
            ),
            user=_reader(),
            address="BUNDLEHASH",
        )
        assert form.is_valid(), form.errors

        form.save()

        assert publish.called is False

    def test_alerts_forms_leave_last_value_unset(self):
        """**A rule arms on its first reading rather than firing on it.**

        Seeding `last_value` here would tell the reader about a crossing that
        happened before they asked to be told about anything - the same mistake
        as a level test, in a different place.
        """
        form = AlertRuleForm(_post(), user=_reader())
        assert form.is_valid(), form.errors

        assert form.save().last_value is None


@pytest.mark.django_db
class TestAlertRuleFormUnits:
    """Testing class for the threshold's unit.

    **Everything is stored in ALGO**, because ALGO is what the engine compares
    against: `unit_price` answers "amount of ALGO for one asset" and the pass
    publishes the page total in ALGO. The reader may say which unit they are
    typing in; the row does not change meaning.
    """

    def _form(self, **overrides):
        data = {
            "subject": Subject.TOTAL_VALUE,
            "direction": Direction.DOWN,
            "threshold": "100",
        }
        data.update(overrides)
        return AlertRuleForm(data, user=_reader(), address="BUNDLE")

    def test_alerts_forms_algo_is_stored_as_typed(self):
        form = self._form(threshold_unit="algo")

        assert form.is_valid(), form.errors
        assert form.cleaned_data["threshold"] == Decimal("100")

    def test_alerts_forms_usd_is_converted(self):
        """100 USD at $0.25 an ALGO is 400 ALGO."""
        form = self._form(threshold_unit="usd", algo_usd="0.25")

        assert form.is_valid(), form.errors
        assert form.cleaned_data["threshold"] == Decimal("400")

    def test_alerts_forms_usd_without_a_rate_is_refused(self):
        """**Refused rather than stored unconverted.** A dollar figure kept as
        though it were ALGO is off by whatever an ALGO costs, silently, and the
        rule would fire at a number the reader never chose."""
        form = self._form(threshold_unit="usd")

        assert form.is_valid() is False
        assert "not available" in str(form.errors["threshold"])

    def test_alerts_forms_a_missing_unit_means_algo(self):
        """An older cached panel posts no unit, and has to keep meaning what it
        always meant."""
        form = self._form()

        assert form.is_valid(), form.errors
        assert form.cleaned_data["threshold_unit"] == "algo"

    def test_alerts_forms_a_percentage_ignores_the_unit(self):
        """**A percentage is not a currency.** The template hides the control
        there, so any value posted is stale - and converting "5%" by an ALGO
        price would make it something else entirely."""
        form = self._form(
            subject=Subject.TOTAL_PERCENT,
            window_seconds=3600,
            threshold="5",
            threshold_unit="usd",
            algo_usd="0.25",
        )

        assert form.is_valid(), form.errors
        assert form.cleaned_data["threshold"] == Decimal("5")
        assert form.cleaned_data["threshold_unit"] == "algo"

    def test_alerts_forms_the_rate_comes_from_the_form(self):
        """Posted back rather than fetched again at save, so the number the
        reader was shown is the number they are held to."""
        assert "algo_usd" in AlertRuleForm(user=_reader()).fields

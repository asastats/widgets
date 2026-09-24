"""Testing module for :py:mod:`widgets.inhouse.alerts.views` module."""

import hashlib
import hmac
import inspect
import json
import logging

import pytest
from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import RequestFactory
from django.utils import timezone

from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS
from utils.helpers import bundle_from_addresses
from widgets.inhouse.alerts.forms import AlertRuleForm
from widgets.inhouse.alerts.models import (
    AlertRule,
    Direction,
    PushSubscription,
    Subject,
)
from widgets.inhouse.alerts.views import (
    SIGNATURE_HEADER,
    AlertsPricedView,
    AlertsRepricedView,
    AlertsRuleDeleteView,
    AlertsRuleEditView,
    AlertsRulesView,
    AlertsSubscribeView,
    AlertsUnsubscribeView,
    AlertsView,
    signature_ok,
)


def _reader(tier="Professional", email="views@example.com"):
    """Return a user whose profile sits at `tier`."""
    user = get_user_model().objects.create_user(
        username=email, email=email, password="x"
    )
    profile = user.profile
    profile.permission = SUBSCRIPTION_TIER_PERMISSIONS[tier]
    profile.save()
    return user


@pytest.fixture
def reader_pro(db):
    """A reader whose tier admits 25 rules."""
    return _reader(email="create@example.com")


def _rule(user, **overrides):
    """Store and return one rule for `user`."""
    fields = {
        "user": user,
        "subject": Subject.ASA_PRICE,
        "direction": Direction.DOWN,
        "threshold": "1",
        "asset_id": 1,
    }
    fields.update(overrides)
    return AlertRule.objects.create(**fields)


class TestInhouseAlertsViewsGate:
    """Testing class for how each view resolves its page and gates."""

    @pytest.mark.parametrize(
        "view_class",
        [AlertsView, AlertsRulesView, AlertsRuleDeleteView, AlertsRuleEditView],
    )
    def test_inhouse_alerts_views_test_func_resolves_and_gates(
        self, mocker, view_class
    ):
        """**All four, because all four take a page in the URL.** A view that
        skipped the resolver would accept whatever was in the path, and the
        manifest gate is what bands the widget by address count.
        """
        view = view_class()
        # **`kwargs`, not `args`.** Django sends every group as a keyword when
        # any one of them is named, and the delete route names `pk` - so a view
        # reading `self.args[0]` worked on two routes and raised `IndexError`
        # on the third. See `test_the_delete_route_really_reaches_its_gate`.
        view.kwargs = {"page": "abcdef"}
        resolver = mocker.patch(
            "widgets.inhouse.alerts.views.bundle_and_addresses_from_path",
            return_value=("BUNDLEHASH", "ADDR_ONE ADDR_TWO"),
        )
        gate = mocker.patch.object(view, "manifest_test_func", return_value=True)

        assert view.test_func() is True
        resolver.assert_called_once_with("ABCDEF", force_bundle=True)
        gate.assert_called_once_with(2)
        assert view.bundle == "BUNDLEHASH"


@pytest.mark.django_db
class TestInhouseAlertsViewsContext:
    """Testing class for the shared context."""

    def test_inhouse_alerts_views_context_counts_only_this_reader(self, mocker):
        mine = _reader(email="mine@example.com")
        theirs = _reader(email="theirs@example.com")
        _rule(mine)
        _rule(theirs)
        _rule(theirs)

        view = AlertsView()
        view.request = mocker.MagicMock(user=mine)

        assert view.alerts_context("B")["rules_kept"] == 1

    def test_inhouse_alerts_views_context_sends_the_remainder(self, mocker):
        """The template never subtracts; a second place doing that arithmetic is
        a second place to get it wrong."""
        reader = _reader(tier="Asastatser")  # five
        _rule(reader)
        _rule(reader)

        view = AlertsView()
        view.request = mocker.MagicMock(user=reader)
        context = view.alerts_context("B")

        assert (context["rules_allowed"], context["rules_left"]) == (5, 3)

    def test_inhouse_alerts_views_context_never_goes_negative(self, mocker):
        """A cap lowered under a reader who is already over it - a downgrade, or
        a change to the table - must read zero rather than a negative, which the
        template would render as "-2 of 5 left"."""
        reader = _reader(tier="Asastatser")
        for index in range(7):
            _rule(reader, asset_id=index)

        view = AlertsView()
        view.request = mocker.MagicMock(user=reader)

        assert view.alerts_context("B")["rules_left"] == 0

    def test_inhouse_alerts_views_context_marks_an_unentitled_reader(
        self, mocker
    ):
        """Zero is both "not subscribed" and "used them all", and the modal says
        different things about each - so the context distinguishes them."""
        view = AlertsView()
        view.request = mocker.MagicMock(user=_reader(tier="Intro"))
        context = view.alerts_context("B")

        assert context["alerts_entitled"] is False
        assert context["rules_left"] == 0

    def test_inhouse_alerts_views_context_omits_inactive_rules(self, mocker):
        reader = _reader()
        _rule(reader)
        _rule(reader, active=False)

        view = AlertsView()
        view.request = mocker.MagicMock(user=reader)

        assert view.alerts_context("B")["rules_kept"] == 1


@pytest.mark.django_db
class TestInhouseAlertsViewsDelete:
    """Testing class for removing a rule.

    **The scoping is the point of this class.** A rule id is a guessable
    integer, so the lookup is by `(pk, user)` rather than by pk followed by an
    ownership check - the second shape is one forgotten line away from letting
    anybody delete anybody's alerts.
    """

    @pytest.mark.parametrize(
        ("subject", "republished"),
        [
            (Subject.ASA_PRICE, True),
            (Subject.ASA_PRICE_PERCENT, True),
            (Subject.ASA_TOTAL, False),
            (Subject.TOTAL_VALUE, False),
        ],
    )
    def test_inhouse_alerts_views_delete_republishes_a_priced_asset(
        self, mocker, subject, republished
    ):
        """**Recomputed, not decremented**, and only when it can have changed.

        The asset may still be named by somebody else's rule, so
        `publish_assets` asks the database - but asking at all is only worth a
        query when the deleted rule was one the price task cared about. Both
        priced subjects count; `asa_total` names an asset and does not.
        """
        reader = _reader(email=f"delete-{subject}@example.com")
        rule = _rule(reader, subject=subject, asset_id=31566704)
        view = AlertsRuleDeleteView()
        view.kwargs = {"pk": rule.pk}
        view.bundle = "B"
        view.request = mocker.MagicMock(user=reader)
        mocker.patch(
            "widgets.inhouse.alerts.views.render_to_string", return_value=""
        )
        mocker.patch("widgets.inhouse.alerts.views.publish_page")
        publish = mocker.patch("widgets.inhouse.alerts.views.publish_assets")

        view.post(view.request)

        assert publish.called is republished

    def test_inhouse_alerts_views_delete_removes_the_readers_own_rule(
        self, mocker
    ):
        reader = _reader()
        rule = _rule(reader)
        view = AlertsRuleDeleteView()
        view.kwargs = {"pk": rule.pk}
        view.bundle = "B"
        # `self.request` is what Django's `setup()` would have set; the
        # mixin reads it rather than the argument, as every CBV does.
        view.request = mocker.MagicMock(user=reader)
        mocker.patch(
            "widgets.inhouse.alerts.views.render_to_string", return_value=""
        )

        view.post(view.request)

        assert AlertRule.objects.filter(pk=rule.pk).exists() is False

    def test_inhouse_alerts_views_delete_refuses_another_readers_rule(
        self, mocker
    ):
        """**A 404, which is also the right answer**: the rule is not theirs to
        know about, so "not found" is both the safe response and the true one.
        """
        owner = _reader(email="owner@example.com")
        attacker = _reader(email="attacker@example.com")
        rule = _rule(owner)
        view = AlertsRuleDeleteView()
        view.kwargs = {"pk": rule.pk}
        view.bundle = "B"

        view.request = mocker.MagicMock(user=attacker)

        with pytest.raises(Http404):
            view.post(view.request)

        assert AlertRule.objects.filter(pk=rule.pk).exists() is True


@pytest.mark.django_db
class TestInhouseAlertsViewsModal:
    """Testing class for the modal's own context."""

    def test_inhouse_alerts_views_modal_context_carries_the_rules(self, mocker):
        reader = _reader()
        _rule(reader)
        view = AlertsView()
        view.request = mocker.MagicMock(user=reader)
        view.bundle = "BUNDLEHASH"
        view.kwargs = {}

        context = view.get_context_data()

        assert context["address"] == "BUNDLEHASH"
        assert context["rules_kept"] == 1
        # The form's choices are server-rendered, so anything else the browser
        # posts was typed by hand - which `test_forms` relies on.
        assert len(context["subjects"]) == 6
        assert len(context["windows"]) == 4

    def test_inhouse_alerts_views_modal_is_not_capped_with_room_left(self, mocker):
        reader = _reader(tier="Asastatser")
        _rule(reader)
        view = AlertsView()
        view.request = mocker.MagicMock(user=reader)
        view.bundle = "BUNDLEHASH"
        view.kwargs = {}

        context = view.get_context_data()

        assert context["rules_capped"] is False

    def test_inhouse_alerts_views_modal_says_when_the_allowance_is_spent(
        self, mocker
    ):
        """**The number needs a sentence next to it at the limit.**

        "0 of 5 left" on its own reads as something being broken. The reason and
        the way out belong beside the count rather than only where the form used
        to be - that sentence is below the fold on a phone, and is not rendered
        at all while the reader is editing a rule.
        """
        reader = _reader(tier="Asastatser")
        for asset_id in range(1, 6):
            _rule(reader, asset_id=asset_id)
        view = AlertsView()
        view.request = mocker.MagicMock(user=reader)
        view.bundle = "BUNDLEHASH"
        view.kwargs = {}

        context = view.get_context_data()

        assert context["rules_left"] == 0
        assert context["rules_capped"] is True
        assert context["more_rules_available"] is True

    def test_inhouse_alerts_views_modal_offers_the_top_tier_no_upgrade(
        self, mocker
    ):
        """A Cluster reader at their cap already has the largest allowance sold.

        Sending them to the plans page is an invitation to buy what they have,
        which reads as the site not knowing what they bought.
        """
        reader = _reader(tier="Cluster")
        view = AlertsView()
        view.request = mocker.MagicMock(user=reader)
        view.bundle = "BUNDLEHASH"
        view.kwargs = {}

        context = view.get_context_data()

        assert context["more_rules_available"] is False


@pytest.mark.django_db
class TestInhouseAlertsViewsCreate:
    """Testing class for creating a rule through the endpoint."""

    def _view(self, mocker, reader, post):
        view = AlertsRulesView()
        view.bundle = "BUNDLEHASH"
        view.addresses = "ADDR_ONE ADDR_TWO"
        view.request = mocker.MagicMock(user=reader, POST=post)
        return view

    def test_inhouse_alerts_views_create_stores_and_answers_200(
        self, reader_pro, mocker
    ):
        rendered = mocker.patch(
            "widgets.inhouse.alerts.views.render_to_string", return_value="<div/>"
        )
        view = self._view(
            mocker,
            reader_pro,
            {
                "subject": Subject.TOTAL_VALUE,
                "direction": Direction.DOWN,
                "threshold": "100",
            },
        )

        response = view.post(view.request)

        assert response.status_code == 200
        assert AlertRule.objects.filter(user=reader_pro).count() == 1
        assert rendered.call_args.args[0] == "alerts/_panel.html"

    def test_inhouse_alerts_views_create_stores_the_page_it_was_made_from(
        self, reader_pro, mocker
    ):
        mocker.patch(
            "widgets.inhouse.alerts.views.render_to_string", return_value=""
        )
        view = self._view(
            mocker,
            reader_pro,
            {
                "subject": Subject.TOTAL_VALUE,
                "direction": Direction.DOWN,
                "threshold": "100",
            },
        )

        view.post(view.request)

        # The engine's page key, not the addresses it was made from: rules
        # stored under a joined list matched `lvp:` for nothing and never
        # fired. This assertion used to pin that bug.
        stored = AlertRule.objects.get(user=reader_pro).address
        assert stored == bundle_from_addresses("ADDR_ONE ADDR_TWO")
        assert " " not in stored

    def test_inhouse_alerts_views_create_survives_a_long_bundle(
        self, reader_pro, mocker
    ):
        """**Reported as an internal server error on 2026-09-24.**

        `address` is 128 characters. Three addresses joined are 176, so the
        insert raised `StringDataRightTruncation` and the reader was shown the
        500 page - twice, and again after deleting a rule to make room, because
        nothing about it was a capacity problem. The page key is 58 characters
        at most whatever the bundle holds.
        """
        mocker.patch(
            "widgets.inhouse.alerts.views.render_to_string", return_value=""
        )
        view = self._view(
            mocker,
            reader_pro,
            {
                "subject": Subject.TOTAL_VALUE,
                "direction": Direction.DOWN,
                "threshold": "100",
            },
        )
        view.addresses = " ".join(f"{letter * 58}" for letter in "ABCD")

        view.post(view.request)

        assert len(AlertRule.objects.get(user=reader_pro).address) <= 58

    def test_inhouse_alerts_views_create_answers_422_on_a_bad_rule(
        self, reader_pro, mocker
    ):
        """**422, not 400.** The request was well-formed and the values were
        not, which is the distinction htmx's own error handling makes - and a
        400 would read as "the browser sent nonsense" in a log."""
        mocker.patch(
            "widgets.inhouse.alerts.views.render_to_string", return_value=""
        )
        view = self._view(
            mocker,
            reader_pro,
            # An asset subject with no asset: a rule that would watch nothing.
            {
                "subject": Subject.ASA_PRICE,
                "direction": Direction.DOWN,
                "threshold": "1",
            },
        )

        response = view.post(view.request)

        assert response.status_code == 422
        assert AlertRule.objects.count() == 0

    def test_inhouse_alerts_views_create_keeps_the_bound_form_when_it_fails(
        self, reader_pro, mocker
    ):
        """So the panel can show the error. A fresh form would render the
        message away and leave the reader with a silently unchanged list."""
        rendered = mocker.patch(
            "widgets.inhouse.alerts.views.render_to_string", return_value=""
        )
        view = self._view(
            mocker, reader_pro, {"subject": Subject.ASA_PRICE, "threshold": "1"}
        )

        view.post(view.request)

        assert rendered.call_args.args[1]["form"].errors

    def test_inhouse_alerts_views_create_hands_back_a_blank_form_on_success(
        self, reader_pro, mocker
    ):
        """The reader has just written one; the next thing they see should be an
        empty form rather than their own values waiting to be sent again."""
        rendered = mocker.patch(
            "widgets.inhouse.alerts.views.render_to_string", return_value=""
        )
        view = self._view(
            mocker,
            reader_pro,
            {
                "subject": Subject.TOTAL_VALUE,
                "direction": Direction.DOWN,
                "threshold": "100",
            },
        )

        view.post(view.request)

        assert rendered.call_args.args[1]["form"].is_bound is False


@pytest.mark.django_db
class TestInhouseAlertsViewsSubscribe:
    """Testing class for registering a browser.

    **The endpoint comes from the browser, not from us.** `PushManager.subscribe`
    returns a URL at a push service plus the keys to encrypt for it; the view
    stores what it was handed against whoever is signed in.
    """

    def _view(self, mocker, reader, body, agent="Firefox"):
        view = AlertsSubscribeView()
        view.request = mocker.MagicMock(
            user=reader,
            body=json.dumps(body).encode() if body is not None else b"",
            META={"HTTP_USER_AGENT": agent},
        )
        return view

    def _body(self, endpoint="https://push.example/abc"):
        return {"endpoint": endpoint, "keys": {"p256dh": "p", "auth": "a"}}

    def test_inhouse_alerts_views_subscribe_stores_the_browser(
        self, reader_pro, mocker
    ):
        view = self._view(mocker, reader_pro, self._body())

        response = view.post(view.request)

        assert response.status_code == 200
        stored = PushSubscription.objects.get(user=reader_pro)
        assert stored.endpoint == "https://push.example/abc"
        assert (stored.p256dh, stored.auth) == ("p", "a")

    def test_inhouse_alerts_views_subscribe_is_idempotent(
        self, reader_pro, mocker
    ):
        """**A browser re-sends the same subscription on every visit.** Creating
        would hit the unique constraint or pile up rows, so the same endpoint
        must update rather than add."""
        self._view(mocker, reader_pro, self._body()).post(
            self._view(mocker, reader_pro, self._body()).request
        )
        self._view(mocker, reader_pro, self._body()).post(
            self._view(mocker, reader_pro, self._body()).request
        )

        assert PushSubscription.objects.count() == 1

    def test_inhouse_alerts_views_subscribe_rehomes_a_shared_machine(
        self, reader_pro, mocker
    ):
        """**Keyed on the endpoint, so the row follows the browser.**

        One machine, two readers signing in turn. The endpoint belongs to the
        browser rather than the person, so it must move to whoever is signed in
        now - the alternative sends one reader's alerts to another.
        """
        other = get_user_model().objects.create_user(
            username="second@example.com", email="second@example.com", password="x"
        )
        first = self._view(mocker, reader_pro, self._body())
        first.post(first.request)
        second = self._view(mocker, other, self._body())

        second.post(second.request)

        assert PushSubscription.objects.count() == 1
        assert PushSubscription.objects.get().user == other

    def test_inhouse_alerts_views_subscribe_records_the_browser_name(
        self, reader_pro, mocker
    ):
        view = self._view(mocker, reader_pro, self._body(), agent="Safari/17")

        view.post(view.request)

        assert PushSubscription.objects.get().user_agent == "Safari/17"

    def test_inhouse_alerts_views_subscribe_truncates_a_long_agent(
        self, reader_pro, mocker
    ):
        """Truncated rather than validated: it is shown to tell two browsers
        apart and never parsed, so its only requirement is fitting the column.
        """
        view = self._view(mocker, reader_pro, self._body(), agent="x" * 400)

        view.post(view.request)

        assert len(PushSubscription.objects.get().user_agent) == 300

    @pytest.mark.parametrize(
        "body",
        [
            {"keys": {"p256dh": "p", "auth": "a"}},
            {"endpoint": "https://push.example/x", "keys": {"auth": "a"}},
            {"endpoint": "https://push.example/x", "keys": {"p256dh": "p"}},
            {"endpoint": "https://push.example/x"},
        ],
    )
    def test_inhouse_alerts_views_subscribe_refuses_an_incomplete_one(
        self, reader_pro, mocker, body
    ):
        """All three parts are needed to encrypt for a browser. Storing two of
        them yields a row that can never be delivered to and fails per send."""
        view = self._view(mocker, reader_pro, body)

        assert view.post(view.request).status_code == 400
        assert PushSubscription.objects.count() == 0

    def test_inhouse_alerts_views_subscribe_refuses_malformed_json(
        self, reader_pro, mocker
    ):
        view = AlertsSubscribeView()
        view.request = mocker.MagicMock(
            user=reader_pro, body=b"{not json", META={}
        )

        assert view.post(view.request).status_code == 400

    def test_inhouse_alerts_views_subscribe_gates_on_the_manifest(self, mocker):
        view = AlertsSubscribeView()
        gate = mocker.patch.object(view, "manifest_test_func", return_value=True)

        assert view.test_func() is True
        # One, not the page's address count: a browser subscribes for the whole
        # site rather than per page.
        gate.assert_called_once_with(1)


@pytest.mark.django_db
class TestInhouseAlertsViewsUnsubscribe:
    """Testing class for forgetting a browser."""

    def _view(self, mocker, reader, body):
        view = AlertsUnsubscribeView()
        view.request = mocker.MagicMock(
            user=reader, body=json.dumps(body).encode()
        )
        return view

    def test_inhouse_alerts_views_unsubscribe_removes_the_row(
        self, reader_pro, mocker
    ):
        PushSubscription.objects.create(
            user=reader_pro, endpoint="https://push.example/x", p256dh="p", auth="a"
        )
        view = self._view(mocker, reader_pro, {"endpoint": "https://push.example/x"})

        assert view.post(view.request).status_code == 200
        assert PushSubscription.objects.count() == 0

    def test_inhouse_alerts_views_unsubscribe_leaves_another_readers_row(
        self, reader_pro, mocker
    ):
        """**Scoped in the delete itself.** An endpoint is a long opaque string
        rather than a guessable integer, but scoping costs nothing and means a
        leaked one cannot unsubscribe somebody else."""
        other = get_user_model().objects.create_user(
            username="third@example.com", email="third@example.com", password="x"
        )
        PushSubscription.objects.create(
            user=other, endpoint="https://push.example/theirs", p256dh="p", auth="a"
        )
        view = self._view(
            mocker, reader_pro, {"endpoint": "https://push.example/theirs"}
        )

        view.post(view.request)

        assert PushSubscription.objects.count() == 1

    def test_inhouse_alerts_views_unsubscribe_is_idempotent(
        self, reader_pro, mocker
    ):
        """A browser unsubscribing twice, or one whose row was already removed
        as gone, is not an error to report back."""
        view = self._view(mocker, reader_pro, {"endpoint": "https://push.example/x"})

        assert view.post(view.request).status_code == 200

    def test_inhouse_alerts_views_unsubscribe_refuses_malformed_json(
        self, reader_pro, mocker
    ):
        view = AlertsUnsubscribeView()
        view.request = mocker.MagicMock(user=reader_pro, body=b"{not json")

        assert view.post(view.request).status_code == 400

    def test_inhouse_alerts_views_unsubscribe_gates_on_the_manifest(self, mocker):
        view = AlertsUnsubscribeView()
        gate = mocker.patch.object(view, "manifest_test_func", return_value=True)

        assert view.test_func() is True
        gate.assert_called_once_with(1)


class TestInhouseAlertsViewsSignature:
    """Testing class for the one credential the machine caller has."""

    def _request(self, mocker, body=b'{"page": "X"}', offered=None, secret="s3"):
        if offered is None:
            offered = "sha256=" + hmac.new(
                secret.encode(), body, hashlib.sha256
            ).hexdigest()
        return mocker.MagicMock(body=body, META={SIGNATURE_HEADER: offered})

    def test_inhouse_alerts_views_signature_accepts_our_own(
        self, mocker, settings
    ):
        settings.ALERTS_WEBHOOK_SECRET = "s3"

        assert signature_ok(self._request(mocker)) is True

    def test_inhouse_alerts_views_signature_refuses_another_secret(
        self, mocker, settings
    ):
        settings.ALERTS_WEBHOOK_SECRET = "s3"

        assert signature_ok(self._request(mocker, secret="other")) is False

    def test_inhouse_alerts_views_signature_covers_the_body(
        self, mocker, settings
    ):
        """**Signed over the bytes, so changing the page invalidates it.** A
        signature over anything less is a token, and a token replayed with a
        different page notifies the wrong readers."""
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        offered = "sha256=" + hmac.new(
            b"s3", b'{"page": "X"}', hashlib.sha256
        ).hexdigest()

        request = mocker.MagicMock(
            body=b'{"page": "Y"}', META={SIGNATURE_HEADER: offered}
        )

        assert signature_ok(request) is False

    def test_inhouse_alerts_views_signature_refuses_when_unset(
        self, mocker, settings
    ):
        """**An empty secret must not mean "skip the check".**

        The router monitor this copies signs only when it has a secret, which is
        right for something sending and wrong for something receiving: without
        this branch, a deployment that had not configured one would be an
        endpoint anybody could post rule firings to.
        """
        settings.ALERTS_WEBHOOK_SECRET = ""

        # Signed correctly for the empty secret, which is the request an
        # attacker would send if the branch were missing.
        offered = "sha256=" + hmac.new(
            b"", b'{"page": "X"}', hashlib.sha256
        ).hexdigest()
        request = mocker.MagicMock(
            body=b'{"page": "X"}', META={SIGNATURE_HEADER: offered}
        )

        assert signature_ok(request) is False

    def test_inhouse_alerts_views_signature_says_so_in_the_log(
        self, mocker, settings, caplog
    ):
        settings.ALERTS_WEBHOOK_SECRET = ""

        signature_ok(self._request(mocker))

        assert "no secret configured" in caplog.text

    def test_inhouse_alerts_views_signature_refuses_an_absent_header(
        self, mocker, settings
    ):
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        request = mocker.MagicMock(body=b'{"page": "X"}', META={})

        assert signature_ok(request) is False

    def test_inhouse_alerts_views_signature_compares_in_constant_time(self):
        """**`compare_digest`, never `==`.** Read off the source rather than
        timed: a timing test is flaky, while the wrong comparison is a single
        identifier and is exactly what a later edit would reintroduce."""
        source = inspect.getsource(signature_ok)

        assert "hmac.compare_digest" in source


class TestInhouseAlertsViewsRepriced:
    """Testing class for the engine's trigger."""

    def _post(self, mocker, body, signed=True, secret="s3"):
        raw = json.dumps(body).encode() if not isinstance(body, bytes) else body
        offered = (
            "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
            if signed
            else "sha256=wrong"
        )
        request = mocker.MagicMock(body=raw, META={SIGNATURE_HEADER: offered})
        return AlertsRepricedView().post(request)

    def test_inhouse_alerts_views_repriced_refuses_an_unsigned_call(
        self, mocker, settings
    ):
        settings.ALERTS_WEBHOOK_SECRET = "s3"

        response = self._post(mocker, {"page": "X"}, signed=False)

        assert response.status_code == 403

    def test_inhouse_alerts_views_repriced_checks_the_signature_first(
        self, mocker, settings
    ):
        """**Before the body is parsed or Redis is touched.** An endpoint that
        did work for an unsigned caller is an endpoint an unsigned caller can
        use, whatever it answers them."""
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        payload = mocker.patch("widgets.inhouse.alerts.views.payload_for")

        self._post(mocker, {"page": "X"}, signed=False)

        assert payload.called is False

    def test_inhouse_alerts_views_repriced_refuses_malformed_json(
        self, mocker, settings
    ):
        settings.ALERTS_WEBHOOK_SECRET = "s3"

        assert self._post(mocker, b"{not json").status_code == 400

    def test_inhouse_alerts_views_repriced_refuses_a_body_naming_no_page(
        self, mocker, settings
    ):
        settings.ALERTS_WEBHOOK_SECRET = "s3"

        assert self._post(mocker, {}).status_code == 400

    def test_inhouse_alerts_views_repriced_accepts_an_empty_body(
        self, mocker, settings
    ):
        """`request.body` is empty rather than absent on a POST with no content,
        and `json.loads(b"")` raises - so the view reads `or "{}"`, and this is
        the path that proves it answers 400 rather than 500."""
        settings.ALERTS_WEBHOOK_SECRET = "s3"

        assert self._post(mocker, b"").status_code == 400

    def test_inhouse_alerts_views_repriced_is_quiet_when_nothing_published(
        self, mocker, settings
    ):
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        mocker.patch(
            "widgets.inhouse.alerts.views.payload_for", return_value=None
        )
        evaluate = mocker.patch("widgets.inhouse.alerts.views.evaluate_page")

        response = self._post(mocker, {"page": "X"})

        assert response.status_code == 200
        assert json.loads(response.content)["fired"] == 0
        assert evaluate.called is False

    def test_inhouse_alerts_views_repriced_says_so_in_the_log(
        self, mocker, settings, caplog
    ):
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        mocker.patch(
            "widgets.inhouse.alerts.views.payload_for", return_value=None
        )

        self._post(mocker, {"page": "X"})

        assert "nothing published" in caplog.text

    def test_inhouse_alerts_views_repriced_notifies_what_fired(
        self, reader_pro, mocker, settings
    ):
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        rule = _rule(reader_pro, address="X")
        mocker.patch(
            "widgets.inhouse.alerts.views.payload_for", return_value={"total": 1}
        )
        mocker.patch(
            "widgets.inhouse.alerts.views.evaluate_page",
            return_value=([rule], 0),
        )
        notify = mocker.patch(
            "widgets.inhouse.alerts.views.notify", return_value=2
        )

        response = self._post(mocker, {"page": "X"})

        assert json.loads(response.content) == {
            "ok": True,
            "fired": 1,
            "notified": 2,
        }
        assert notify.call_args.args[0] == reader_pro

    def test_inhouse_alerts_views_repriced_sends_the_page_to_open(
        self, reader_pro, mocker, settings
    ):
        """The notification has to land somewhere, and the page the rule was
        evaluated on is the only place the reader can see what moved."""
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        rule = _rule(reader_pro, address="X")
        mocker.patch(
            "widgets.inhouse.alerts.views.payload_for", return_value={"total": 1}
        )
        mocker.patch(
            "widgets.inhouse.alerts.views.evaluate_page",
            return_value=([rule], 0),
        )
        notify = mocker.patch(
            "widgets.inhouse.alerts.views.notify", return_value=1
        )

        self._post(mocker, {"page": "X"})

        message = notify.call_args.args[1]
        assert message["url"] == "/X"
        assert message["tag"] == f"alert-{rule.pk}"

    def test_inhouse_alerts_views_repriced_reports_what_it_skipped(
        self, mocker, settings, caplog
    ):
        """**Skipped loudly.** A rule that is stored, looks active and is never
        examined is the failure this whole endpoint could hide."""
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        mocker.patch(
            "widgets.inhouse.alerts.views.payload_for", return_value={"total": 1}
        )
        mocker.patch(
            "widgets.inhouse.alerts.views.evaluate_page", return_value=([], 3)
        )

        with caplog.at_level(logging.INFO):
            self._post(mocker, {"page": "X"})

        assert "3 rule(s) on X not evaluated here" in caplog.text

    def test_inhouse_alerts_views_repriced_takes_no_session(self):
        """**No `WidgetAccessMixin`, deliberately.** Every other view here is
        reached by a signed-in reader; this one is reached by the engine, which
        has no session. Mixing the gates would mean a machine caller needing a
        login."""
        from widgethost.enforcement import WidgetAccessMixin

        assert not issubclass(AlertsRepricedView, WidgetAccessMixin)


class TestInhouseAlertsViewsPriced:
    """Testing class for the periodic price task's endpoint."""

    def _post(self, mocker, body, signed=True, secret="s3"):
        raw = json.dumps(body).encode() if not isinstance(body, bytes) else body
        offered = (
            "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
            if signed
            else "sha256=wrong"
        )
        request = mocker.MagicMock(body=raw, META={SIGNATURE_HEADER: offered})
        return AlertsPricedView().post(request)

    def test_inhouse_alerts_views_priced_refuses_an_unsigned_call(
        self, mocker, settings
    ):
        """**The body is an answer here, not a trigger.** The website acts on a
        number it cannot check against anything, so the signature is the whole
        of the trust."""
        settings.ALERTS_WEBHOOK_SECRET = "s3"

        assert self._post(mocker, {"prices": {}}, signed=False).status_code == 403

    def test_inhouse_alerts_views_priced_checks_the_signature_first(
        self, mocker, settings
    ):
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        evaluate = mocker.patch("widgets.inhouse.alerts.views.evaluate_prices")

        self._post(mocker, {"prices": {"1": 1.0}}, signed=False)

        assert evaluate.called is False

    def test_inhouse_alerts_views_priced_refuses_malformed_json(
        self, mocker, settings
    ):
        settings.ALERTS_WEBHOOK_SECRET = "s3"

        assert self._post(mocker, b"{not json").status_code == 400

    def test_inhouse_alerts_views_priced_refuses_a_body_with_no_prices(
        self, mocker, settings
    ):
        settings.ALERTS_WEBHOOK_SECRET = "s3"

        assert self._post(mocker, {}).status_code == 400

    def test_inhouse_alerts_views_priced_refuses_prices_of_the_wrong_shape(
        self, mocker, settings
    ):
        """A list would iterate as keys and produce a puzzle rather than a 400."""
        settings.ALERTS_WEBHOOK_SECRET = "s3"

        assert self._post(mocker, {"prices": [1, 2]}).status_code == 400

    def test_inhouse_alerts_views_priced_reads_asset_ids_as_integers(
        self, mocker, settings
    ):
        """**JSON has no integer keys, and the rules store integers.**

        Without the conversion `prices.get(rule.asset_id)` misses every asset
        silently, which reads exactly like "nothing moved" - the whole feature
        quietly doing nothing while every part of it reports success.
        """
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        evaluate = mocker.patch(
            "widgets.inhouse.alerts.views.evaluate_prices", return_value=[]
        )

        self._post(mocker, {"prices": {"31566704": 0.25}})

        assert evaluate.call_args.args[0] == {31566704: 0.25}

    def test_inhouse_alerts_views_priced_keeps_a_null_price(self, mocker, settings):
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        evaluate = mocker.patch(
            "widgets.inhouse.alerts.views.evaluate_prices", return_value=[]
        )

        self._post(mocker, {"prices": {"1": None}})

        assert evaluate.call_args.args[0] == {1: None}

    def test_inhouse_alerts_views_priced_drops_an_unusable_entry(
        self, mocker, settings
    ):
        """One bad entry must not cost every other reader their alerts."""
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        evaluate = mocker.patch(
            "widgets.inhouse.alerts.views.evaluate_prices", return_value=[]
        )

        self._post(mocker, {"prices": {"1": 1.0, "nonsense": "x"}})

        assert evaluate.call_args.args[0] == {1: 1.0}

    def test_inhouse_alerts_views_priced_says_so_for_an_unusable_entry(
        self, mocker, settings, caplog
    ):
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        mocker.patch(
            "widgets.inhouse.alerts.views.evaluate_prices", return_value=[]
        )

        self._post(mocker, {"prices": {"nonsense": "x"}})

        assert "unusable price for asset" in caplog.text

    def test_inhouse_alerts_views_priced_notifies_what_fired(
        self, reader_pro, mocker, settings
    ):
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        rule = _rule(reader_pro)
        mocker.patch(
            "widgets.inhouse.alerts.views.evaluate_prices", return_value=[rule]
        )
        notify = mocker.patch(
            "widgets.inhouse.alerts.views.notify", return_value=2
        )

        response = self._post(mocker, {"prices": {"1": 1.0}})

        assert json.loads(response.content) == {
            "ok": True,
            "assets": 1,
            "fired": 1,
            "notified": 2,
        }
        assert notify.call_args.args[0] == reader_pro

    def test_inhouse_alerts_views_priced_opens_the_site_not_a_page(
        self, reader_pro, mocker, settings
    ):
        """A price rule belongs to an asset rather than to a page, so there is
        no address to send the reader to."""
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        rule = _rule(reader_pro)
        mocker.patch(
            "widgets.inhouse.alerts.views.evaluate_prices", return_value=[rule]
        )
        notify = mocker.patch(
            "widgets.inhouse.alerts.views.notify", return_value=1
        )

        self._post(mocker, {"prices": {"1": 1.0}})

        assert notify.call_args.args[1]["url"] == "/"

    def test_inhouse_alerts_views_priced_discloses_the_pool_depth(
        self, db, mocker, settings
    ):
        """**The decision, end to end through the endpoint.**

        The engine measures what the asset's pools hold at the moment it
        prices, sends it beside the price, and the reader is told - rather than
        the rule being refused at creation or suppressed without explanation.
        """
        reader = _reader(email="depth@example.com")
        PushSubscription.objects.create(
            user=reader, endpoint="https://push.example/d", p256dh="p", auth="a"
        )
        _rule(reader, subject=Subject.ASA_PRICE, asset_id=1, last_value="2")
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        notify = mocker.patch(
            "widgets.inhouse.alerts.views.notify", return_value=1
        )

        self._post(mocker, {"prices": {"1": 0.5}, "depths": {"1": 340.0}})

        assert "pools hold ~340.00 ALGO" in notify.call_args[0][1]["body"]

    def test_inhouse_alerts_views_priced_without_depths_still_notifies(
        self, db, mocker, settings
    ):
        """An engine that has not caught up sends no `depths`, and the two
        repos sync separately - so the alert has to arrive with less said
        rather than not arrive."""
        reader = _reader(email="nodepth@example.com")
        PushSubscription.objects.create(
            user=reader, endpoint="https://push.example/n", p256dh="p", auth="a"
        )
        _rule(reader, subject=Subject.ASA_PRICE, asset_id=1, last_value="2")
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        notify = mocker.patch(
            "widgets.inhouse.alerts.views.notify", return_value=1
        )

        self._post(mocker, {"prices": {"1": 0.5}})

        body = notify.call_args[0][1]["body"]
        assert "pools hold" not in body
        assert "1 price falls below" in body

    def test_inhouse_alerts_views_priced_ignores_an_unusable_depth(
        self, db, mocker, settings
    ):
        """A depth that will not parse costs the reader a sentence, never the
        alert."""
        reader = _reader(email="baddepth@example.com")
        PushSubscription.objects.create(
            user=reader, endpoint="https://push.example/b", p256dh="p", auth="a"
        )
        _rule(reader, subject=Subject.ASA_PRICE, asset_id=1, last_value="2")
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        mocker.patch("widgets.inhouse.alerts.views.notify", return_value=1)

        response = self._post(
            mocker, {"prices": {"1": 0.5}, "depths": {"1": "deep"}}
        )

        assert json.loads(response.content)["fired"] == 1

    def test_inhouse_alerts_views_priced_tags_each_rule_separately(
        self, reader_pro, mocker, settings
    ):
        """A shared tag makes the browser replace one notification with the
        next, so two alerts firing together would show as one."""
        settings.ALERTS_WEBHOOK_SECRET = "s3"
        one, two = _rule(reader_pro), _rule(reader_pro, asset_id=2)
        mocker.patch(
            "widgets.inhouse.alerts.views.evaluate_prices", return_value=[one, two]
        )
        notify = mocker.patch(
            "widgets.inhouse.alerts.views.notify", return_value=1
        )

        self._post(mocker, {"prices": {"1": 1.0}})

        tags = {call.args[1]["tag"] for call in notify.call_args_list}
        assert tags == {f"alert-{one.pk}", f"alert-{two.pk}"}

    def test_inhouse_alerts_views_priced_takes_no_session(self):
        from widgethost.enforcement import WidgetAccessMixin

        assert not issubclass(AlertsPricedView, WidgetAccessMixin)


@pytest.mark.django_db
class TestInhouseAlertsViewsLiveFlag:
    """Testing class for the modal's "not switched on" notice."""

    def _context(self, mocker):
        view = AlertsView()
        view.request = mocker.MagicMock(user=_reader(email="live@example.com"))
        return view.alerts_context("B")

    def test_inhouse_alerts_views_is_not_live_without_a_secret(
        self, mocker, settings
    ):
        """**Without the shared secret both receiving endpoints refuse every
        call**, so no rule can fire however complete the code is. A modal that
        took rules without saying so would promise what the deployment cannot
        do."""
        settings.ALERTS_WEBHOOK_SECRET = ""

        assert self._context(mocker)["alerts_live"] is False

    def test_inhouse_alerts_views_is_live_with_a_secret(self, mocker, settings):
        settings.ALERTS_WEBHOOK_SECRET = "s3"

        assert self._context(mocker)["alerts_live"] is True


@pytest.mark.django_db
class TestInhouseAlertsViewsRejectedFormKeepsInput:
    """Testing class for what a rejected rule leaves in the form.

    **The panel that comes back replaces the one the reader filled in.** The
    fields are hand-written markup rather than `{{ form.subject }}`, so nothing
    repopulated them: fixing a threshold typed as "0" meant entering the
    subject, the direction, the asset and the period all over again.
    """

    def _post(self, reader, **overrides):
        data = {
            "subject": Subject.ASA_PRICE,
            "direction": Direction.UP,
            "threshold": "0",  # refused, which is the point
            "asset_id": "31566704",
            "threshold_unit": "usd",
            "algo_usd": "0.25",
        }
        data.update(overrides)
        view = AlertsRulesView()
        view.bundle = "A" * 58
        view.addresses = "A" * 58
        view.request = RequestFactory().post("/", data)
        view.request.user = reader
        return view.post(view.request).content.decode()

    def test_inhouse_alerts_views_rejected_keeps_the_subject(self, reader_pro):
        html = self._post(reader_pro)

        assert 'value="asa_price"\n          selected' in html or (
            'value="asa_price"' in html and "selected" in html
        )

    def test_inhouse_alerts_views_rejected_keeps_the_threshold(self, reader_pro):
        html = self._post(reader_pro, threshold="-5")

        assert 'value="-5"' in html

    def test_inhouse_alerts_views_rejected_keeps_the_asset(self, reader_pro):
        """The id is all a bound form carries - the unit and the name were only
        ever on the search row - so the button falls back to `#<id>`. The choice
        preserved beats the label preserved."""
        html = self._post(reader_pro)

        assert 'class="alerts-asset-id"' in html
        assert "31566704" in html

    def test_inhouse_alerts_views_rejected_keeps_the_unit(self, reader_pro):
        html = self._post(reader_pro)

        assert 'class="alerts-unit-value"' in html
        assert 'value="usd"' in html

    def test_inhouse_alerts_views_rejected_keeps_the_period(self, reader_pro):
        html = self._post(
            reader_pro,
            subject=Subject.TOTAL_PERCENT,
            window_seconds="86400",
            threshold="0",
        )

        assert 'value="86400"' in html
        assert "selected" in html

    def test_inhouse_alerts_views_an_accepted_rule_starts_clean(self, reader_pro):
        """**The opposite case, and it has to stay true.** A rule that saved
        leaves an empty form ready for the next one, not the one just used."""
        html = self._post(reader_pro, threshold="1.5")

        assert 'value="1.5"' not in html


@pytest.mark.django_db
class TestInhouseAlertsViewsUndeliverableRules:
    """Testing class for rules a reader has nowhere to receive.

    **The state is silent and lossy.** A reader who never presses the enable
    button still gets a modal that looks complete: rules save, the page is
    published, the engine triggers, evaluation runs. `notify` then finds no
    subscription and sends nothing - and the rule has already fired, so
    `last_value` is past the threshold and the crossing is spent rather than
    queued.
    """

    def _context(self, mocker, user):
        view = AlertsView()
        view.request = mocker.MagicMock(user=user)
        return view.alerts_context("B")

    def test_inhouse_alerts_views_rules_without_a_browser_are_visible(
        self, mocker
    ):
        reader = _reader(email="nobrowser@example.com")
        _rule(reader)

        context = self._context(mocker, reader)

        assert context["rules_kept"] == 1
        assert context["subscribed_browsers"] == 0

    def test_inhouse_alerts_views_a_subscribed_browser_is_counted(self, mocker):
        reader = _reader(email="withbrowser@example.com")
        _rule(reader)
        PushSubscription.objects.create(
            user=reader,
            endpoint="https://push.example/abc",
            p256dh="p",
            auth="a",
        )

        context = self._context(mocker, reader)

        assert context["subscribed_browsers"] == 1

    def test_inhouse_alerts_views_a_rule_is_held_without_a_browser(self, mocker):
        """**Held, not spent.** Firing it would advance `last_value` past the
        threshold and the crossing would be gone - and the modal promises three
        times over that rules saved now will be there when a browser is on."""
        from widgets.inhouse.alerts.evaluate import evaluate_page

        reader = _reader(email="held@example.com")
        rule = _rule(
            reader,
            subject=Subject.TOTAL_VALUE,
            asset_id=None,
            threshold="100",
            address="PAGE",
            last_value="120",
        )

        fired, _ = evaluate_page("PAGE", {"total": 90})

        assert fired == []
        rule.refresh_from_db()
        assert float(rule.last_value) == 120, "left exactly as it was"
        assert rule.last_fired_at is None, "and no cooldown started"

    def test_inhouse_alerts_views_the_held_crossing_survives_subscribing(
        self, mocker
    ):
        """The whole point of holding: the alert a reader was promised arrives
        once they turn a browser on."""
        from widgets.inhouse.alerts.evaluate import evaluate_page

        reader = _reader(email="later@example.com")
        _rule(
            reader,
            subject=Subject.TOTAL_VALUE,
            asset_id=None,
            threshold="100",
            address="PAGE",
            last_value="120",
        )
        evaluate_page("PAGE", {"total": 90})

        PushSubscription.objects.create(
            user=reader,
            endpoint="https://push.example/later",
            p256dh="p",
            auth="a",
        )
        fired, _ = evaluate_page("PAGE", {"total": 90})

        assert len(fired) == 1

    def test_inhouse_alerts_views_holding_is_said_in_the_log(self, mocker, caplog):
        """"My alert never fired" is the question this answers."""
        import logging

        from widgets.inhouse.alerts.evaluate import evaluate_page

        reader = _reader(email="logged@example.com")
        _rule(
            reader,
            subject=Subject.TOTAL_VALUE,
            asset_id=None,
            threshold="100",
            address="PAGE",
            last_value="120",
        )

        with caplog.at_level(logging.INFO):
            evaluate_page("PAGE", {"total": 90})

        assert "no browser on" in caplog.text


@pytest.mark.django_db
class TestInhouseAlertsViewsEdit:
    """Testing class for changing a rule that already exists."""

    PAGE = "A" * 58

    def _view(self, reader, rule, data=None):
        view = AlertsRuleEditView()
        view.bundle = self.PAGE
        view.addresses = self.PAGE
        view.kwargs = {"page": self.PAGE, "pk": rule.pk}
        factory = RequestFactory()
        view.request = factory.post("/", data) if data else factory.get("/")
        view.request.user = reader
        return view

    def _rule_for(self, reader):
        return _rule(
            reader,
            subject=Subject.TOTAL_VALUE,
            asset_id=None,
            threshold="100",
            address=self.PAGE,
        )

    @pytest.mark.parametrize(
        "subject", [Subject.ASA_PRICE, Subject.ASA_PRICE_PERCENT]
    )
    def test_inhouse_alerts_views_edit_republishes_the_asset_set(
        self, mocker, subject
    ):
        """**An edit can add the first price rule for an asset.**

        `lvra` is what puts an asset in front of the periodic price task, and
        `publish_assets` recomputes it from the database rather than adjusting
        it - so the edit has to say when the answer may have changed.

        Both priced subjects, because `asa_price_percent` needs it *more*: its
        `lvah` series exists only because the price task writes to it, so an
        asset missing from `lvra` means every reading refused, for ever,
        silently.
        """
        reader = _reader(email=f"edit-assets-{subject}@example.com")
        rule = self._rule_for(reader)
        publish = mocker.patch(
            "widgets.inhouse.alerts.views.publish_assets"
        )
        mocker.patch("widgets.inhouse.alerts.views.publish_page")
        mocker.patch("widgets.inhouse.alerts.forms.publish_assets")
        mocker.patch("widgets.inhouse.alerts.forms.publish_page")
        view = self._view(
            reader,
            rule,
            data={
                "subject": subject,
                "direction": Direction.DOWN,
                "threshold": "1",
                "asset_id": "31566704",
                "window_seconds": "3600",
            },
        )

        view.post(view.request)

        assert publish.called is True

    def test_inhouse_alerts_views_edit_leaves_the_asset_set_alone_otherwise(
        self, mocker
    ):
        """A total rule edited into another total rule names no asset, and
        recomputing the set would be a query for an answer that cannot have
        changed."""
        reader = _reader(email="edit-noassets@example.com")
        rule = self._rule_for(reader)
        publish = mocker.patch("widgets.inhouse.alerts.views.publish_assets")
        mocker.patch("widgets.inhouse.alerts.views.publish_page")
        mocker.patch("widgets.inhouse.alerts.forms.publish_assets")
        mocker.patch("widgets.inhouse.alerts.forms.publish_page")
        view = self._view(
            reader,
            rule,
            data={
                "subject": Subject.TOTAL_VALUE,
                "direction": Direction.DOWN,
                "threshold": "250",
            },
        )

        view.post(view.request)

        assert publish.called is False

    def test_inhouse_alerts_views_edit_loads_the_rule_into_the_form(self, mocker):
        reader = _reader(email="edit-load@example.com")
        rule = self._rule_for(reader)
        view = self._view(reader, rule)

        html = view.get(view.request).content.decode()

        assert 'value="100.0000000000"' in html or 'value="100' in html
        assert "Save changes" in html

    def test_inhouse_alerts_views_edit_applies_the_change(self, mocker):
        reader = _reader(email="edit-apply@example.com")
        rule = self._rule_for(reader)
        view = self._view(
            reader,
            rule,
            {
                "subject": Subject.TOTAL_VALUE,
                "direction": Direction.UP,
                "threshold": "250",
            },
        )

        view.post(view.request)

        rule.refresh_from_db()
        assert float(rule.threshold) == 250
        assert rule.direction == Direction.UP

    def test_inhouse_alerts_views_edit_does_not_make_a_second_rule(self, mocker):
        reader = _reader(email="edit-once@example.com")
        rule = self._rule_for(reader)
        view = self._view(
            reader,
            rule,
            {
                "subject": Subject.TOTAL_VALUE,
                "direction": Direction.DOWN,
                "threshold": "250",
            },
        )

        view.post(view.request)

        assert AlertRule.objects.filter(user=reader).count() == 1

    def test_inhouse_alerts_views_edit_re_arms_the_rule(self, mocker):
        """**An edited rule carries no old reading.**

        `last_value` described a comparison against the *previous* threshold.
        Keeping it makes the rule fire on the difference between two rules
        rather than on a crossing: move "falls below 100" to 50 while the last
        reading was 90 and it is suddenly on the other side of its own line,
        through no movement at all.
        """
        reader = _reader(email="edit-arm@example.com")
        rule = self._rule_for(reader)
        rule.last_value = "90"
        rule.last_fired_at = timezone.now()
        rule.save()
        view = self._view(
            reader,
            rule,
            {
                "subject": Subject.TOTAL_VALUE,
                "direction": Direction.DOWN,
                "threshold": "50",
            },
        )

        view.post(view.request)

        rule.refresh_from_db()
        assert rule.last_value is None
        assert rule.last_fired_at is None

    def test_inhouse_alerts_views_edit_works_at_the_limit(self, mocker):
        """**The reader most likely to want to edit is the one who is full.**

        The cap counts kept rules, and the rule being edited is among them - so
        counting it refuses every edit a reader at their limit tries to make,
        with nothing on screen to say why.
        """
        reader = _reader(tier="Asastatser", email="edit-full@example.com")  # five
        rules = [
            _rule(
                reader,
                subject=Subject.TOTAL_VALUE,
                asset_id=None,
                threshold=f"{index + 1}00",
                address=self.PAGE,
            )
            for index in range(5)
        ]
        view = self._view(
            reader,
            rules[0],
            {
                "subject": Subject.TOTAL_VALUE,
                "direction": Direction.DOWN,
                "threshold": "999",
            },
        )

        response = view.post(view.request)

        assert response.status_code == 200
        rules[0].refresh_from_db()
        assert float(rules[0].threshold) == 999

    def test_inhouse_alerts_views_edit_refuses_another_readers_rule(self, mocker):
        """A 404, which is also the true answer: it is not theirs to know
        about."""
        owner = _reader(email="edit-owner@example.com")
        attacker = _reader(email="edit-attacker@example.com")
        rule = self._rule_for(owner)
        view = self._view(attacker, rule)

        with pytest.raises(Http404):
            view.get(view.request)

    def test_inhouse_alerts_views_a_rejected_edit_stays_on_the_rule(self, mocker):
        """**It must not become a new rule.** A rejected change comes back on
        the same one, or the reader's next press creates a duplicate."""
        reader = _reader(email="edit-reject@example.com")
        rule = self._rule_for(reader)
        view = self._view(
            reader,
            rule,
            {
                "subject": Subject.TOTAL_VALUE,
                "direction": Direction.DOWN,
                "threshold": "0",
            },
        )

        response = view.post(view.request)
        html = response.content.decode()

        assert response.status_code == 422
        assert "Save changes" in html
        assert AlertRule.objects.filter(user=reader).count() == 1


class TestInhouseAlertsPanelDom:
    """The markup `alerts.js` reaches into, asserted against the template."""

    def _panel(self):
        """Render the panel with the form on it.

        `rules_left` is what decides whether the form is rendered at all, and a
        panel without it says only "remove one to make room" - 445 characters
        with none of the markup this is about.
        """
        from django.template.loader import render_to_string

        from widgets.inhouse.alerts.models import Direction, Subject

        return render_to_string(
            "alerts/_panel.html",
            {
                "form": AlertRuleForm(user=None, address="A" * 58),
                "address": "A" * 58,
                "rules": [],
                "rules_left": 5,
                "rules_allowed": 5,
                "subjects": Subject.choices,
                "directions": Direction.choices,
                "windows": (),
                "units": (("algo", "ALGO"), ("usd", "USD")),
            },
        )

    def test_inhouse_alerts_panel_keeps_the_unit_inside_the_asset_field(self):
        """**The picker writes the unit, and it writes it inside the field.**

        `chooseAsset` does `field.querySelector(".alerts-asset-unit")` where
        `field` is the row's `.alerts-asset-field` - so an input rendered
        outside it is one the picker never finds. It was rendered forty lines
        away, inside the threshold label, and `if (unit)` swallowed the miss:
        every rule stored a blank unit and every notification named the asset
        by its id. Reported 2026-09-24 as an alert still reading "#393537671".

        The jest fixture had it in the right place, which is why the suite was
        green throughout. This asserts the template instead.
        """
        from html.parser import HTMLParser

        class Nesting(HTMLParser):
            """Record the depth at which the two elements appear."""

            def __init__(self):
                super().__init__()
                self.depth = 0
                self.field_depth = None
                self.unit_inside = False

            def handle_starttag(self, tag, attrs):
                classes = dict(attrs).get("class", "")
                if "alerts-asset-field" in classes:
                    self.field_depth = self.depth
                if "alerts-asset-unit" in classes and self.field_depth is not None:
                    self.unit_inside = self.depth > self.field_depth
                if tag not in ("input", "img", "br", "hr", "meta", "link"):
                    self.depth += 1

            def handle_endtag(self, tag):
                if tag not in ("input", "img", "br", "hr", "meta", "link"):
                    self.depth -= 1
                    if self.field_depth is not None and self.depth == self.field_depth:
                        self.field_depth = None

        parser = Nesting()
        parser.feed(self._panel())

        assert parser.unit_inside, (
            "`.alerts-asset-unit` must be inside `.alerts-asset-field`, or "
            "`chooseAsset` cannot reach it and every rule stores a blank unit"
        )

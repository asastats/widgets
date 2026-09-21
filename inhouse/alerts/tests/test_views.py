"""Testing module for :py:mod:`widgets.inhouse.alerts.views` module."""

import hashlib
import hmac
import inspect
import json
import logging

import pytest
from django.contrib.auth import get_user_model
from django.http import Http404

from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS
from widgets.inhouse.alerts.models import (
    AlertRule,
    Direction,
    PushSubscription,
    Subject,
)
from widgets.inhouse.alerts.views import (
    SIGNATURE_HEADER,
    AlertsRepricedView,
    AlertsRuleDeleteView,
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
        "view_class", [AlertsView, AlertsRulesView, AlertsRuleDeleteView]
    )
    def test_inhouse_alerts_views_test_func_resolves_and_gates(
        self, mocker, view_class
    ):
        """**All three, because all three take a page in the URL.** A view that
        skipped the resolver would accept whatever was in the path, and the
        manifest gate is what bands the widget by address count.
        """
        view = view_class()
        view.args = ["abcdef"]
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
        assert len(context["subjects"]) == 4
        assert len(context["windows"]) == 4


@pytest.mark.django_db
class TestInhouseAlertsViewsCreate:
    """Testing class for creating a rule through the endpoint."""

    def _view(self, mocker, reader, post):
        view = AlertsRulesView()
        view.bundle = "BUNDLEHASH"
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

        assert AlertRule.objects.get(user=reader_pro).address == "BUNDLEHASH"

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

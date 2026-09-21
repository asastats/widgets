"""Testing module for :py:mod:`widgets.inhouse.alerts.push` module."""

import pytest
from django.contrib.auth import get_user_model

from widgets.inhouse.alerts.models import PushSubscription
from widgets.inhouse.alerts.push import notify, push_configured, send_push


@pytest.fixture
def reader(db):
    """Return a user to hang subscriptions on."""
    return get_user_model().objects.create_user(
        username="push@example.com", email="push@example.com", password="x"
    )


def _subscription(reader, endpoint="https://push.example/abc"):
    """Store and return one browser."""
    return PushSubscription.objects.create(
        user=reader, endpoint=endpoint, p256dh="key", auth="auth"
    )


class _Gone(Exception):
    """A `WebPushException` as `pywebpush` raises it, with a response."""

    def __init__(self, status):
        super().__init__(f"gone {status}")
        self.response = type("R", (), {"status_code": status})()


class TestAlertsPushConfigured:
    """Testing class for whether this deployment can send at all."""

    def test_alerts_push_unconfigured_without_keys(self, settings):
        settings.VAPID_PRIVATE_KEY = ""
        settings.VAPID_ADMIN_EMAIL = "mailto:a@b.c"

        assert push_configured() is False

    def test_alerts_push_unconfigured_without_a_contact(self, settings):
        """**The `sub` claim is not optional.** Push services reject a request
        without one, so a deployment holding keys and no contact can sign and
        still not deliver - which would otherwise be discovered per send."""
        settings.VAPID_PRIVATE_KEY = "k"
        settings.VAPID_ADMIN_EMAIL = ""

        assert push_configured() is False

    def test_alerts_push_configured_with_both(self, settings):
        settings.VAPID_PRIVATE_KEY = "k"
        settings.VAPID_ADMIN_EMAIL = "mailto:a@b.c"

        assert push_configured() is True


@pytest.mark.django_db
class TestAlertsSendPush:
    """Testing class for one send."""

    @pytest.fixture(autouse=True)
    def _keys(self, settings):
        settings.VAPID_PRIVATE_KEY = "k"
        settings.VAPID_ADMIN_EMAIL = "mailto:a@b.c"

    def test_alerts_push_sends_and_reports_success(self, reader, mocker):
        webpush = mocker.patch("pywebpush.webpush")

        assert send_push(_subscription(reader), {"title": "hi"}) is True
        assert webpush.called

    def test_alerts_push_passes_the_shape_pywebpush_wants(self, reader, mocker):
        """The endpoint and the client's two keys, nested as the library
        expects - a flat dict is accepted and then fails at encryption."""
        webpush = mocker.patch("pywebpush.webpush")
        subscription = _subscription(reader)

        send_push(subscription, {"title": "hi"})

        info = webpush.call_args.kwargs["subscription_info"]
        assert info["endpoint"] == subscription.endpoint
        assert info["keys"] == {"p256dh": "key", "auth": "auth"}

    @pytest.mark.parametrize("status", [404, 410])
    def test_alerts_push_deletes_a_subscription_that_is_gone(
        self, reader, mocker, status
    ):
        """**The case that decides whether this ages well.**

        404 is "never heard of it" and 410 is "it was here and is gone"; both
        mean the browser is not coming back. Keeping the row turns an ordinary
        end-of-life into a permanent error on every send afterwards.
        """
        mocker.patch("pywebpush.WebPushException", _Gone)
        mocker.patch("pywebpush.webpush", side_effect=_Gone(status))
        subscription = _subscription(reader)

        assert send_push(subscription, {"title": "hi"}) is False
        assert PushSubscription.objects.filter(pk=subscription.pk).exists() is False

    def test_alerts_push_keeps_a_subscription_that_merely_failed(
        self, reader, mocker
    ):
        """A 503 is the push service having a bad minute, not the browser going
        away. Deleting on it would unsubscribe readers during an outage."""
        mocker.patch("pywebpush.WebPushException", _Gone)
        mocker.patch("pywebpush.webpush", side_effect=_Gone(503))
        subscription = _subscription(reader)

        assert send_push(subscription, {"title": "hi"}) is False
        assert PushSubscription.objects.filter(pk=subscription.pk).exists() is True

    def test_alerts_push_does_not_send_without_keys(
        self, reader, mocker, settings
    ):
        """A fork with no keys still runs the site and still stores rules."""
        settings.VAPID_PRIVATE_KEY = ""
        webpush = mocker.patch("pywebpush.webpush")

        assert send_push(_subscription(reader), {"title": "hi"}) is False
        assert webpush.called is False


@pytest.mark.django_db
class TestAlertsNotify:
    """Testing class for notifying a reader rather than a browser."""

    @pytest.fixture(autouse=True)
    def _keys(self, settings):
        settings.VAPID_PRIVATE_KEY = "k"
        settings.VAPID_ADMIN_EMAIL = "mailto:a@b.c"

    def test_alerts_notify_reaches_every_browser(self, reader, mocker):
        """**A subscription is per browser.** A reader with a laptop and a phone
        has two rows, and telling only one is the bug this exists to not have.
        """
        webpush = mocker.patch("pywebpush.webpush")
        _subscription(reader, "https://push.example/laptop")
        _subscription(reader, "https://push.example/phone")

        assert notify(reader, {"title": "hi"}) == 2
        assert webpush.call_count == 2

    def test_alerts_notify_counts_only_what_was_delivered(self, reader, mocker):
        mocker.patch("pywebpush.WebPushException", _Gone)
        mocker.patch("pywebpush.webpush", side_effect=[None, _Gone(410)])
        _subscription(reader, "https://push.example/one")
        _subscription(reader, "https://push.example/two")

        assert notify(reader, {"title": "hi"}) == 1

    def test_alerts_notify_leaves_another_reader_alone(self, reader, mocker):
        webpush = mocker.patch("pywebpush.webpush")
        other = get_user_model().objects.create_user(
            username="other@example.com", email="other@example.com", password="x"
        )
        _subscription(other, "https://push.example/theirs")

        assert notify(reader, {"title": "hi"}) == 0
        assert webpush.called is False

    def test_alerts_notify_a_reader_with_no_browsers_is_not_an_error(
        self, reader, mocker
    ):
        """Every reader starts here, and a rule may fire before they have
        enabled anything."""
        mocker.patch("pywebpush.webpush")

        assert notify(reader, {"title": "hi"}) == 0

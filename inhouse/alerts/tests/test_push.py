"""Testing module for :py:mod:`widgets.inhouse.alerts.push` module."""

import pytest
from django.contrib.auth import get_user_model

from widgets.inhouse.alerts import push
from widgets.inhouse.alerts.models import NativePushDevice, PushSubscription
from widgets.inhouse.alerts.push import (
    native_push_configured,
    notify,
    push_configured,
    send_native_push,
    send_push,
)


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

    def test_alerts_push_keeps_a_subscription_that_merely_failed(self, reader, mocker):
        """A 503 is the push service having a bad minute, not the browser going
        away. Deleting on it would unsubscribe readers during an outage."""
        mocker.patch("pywebpush.WebPushException", _Gone)
        mocker.patch("pywebpush.webpush", side_effect=_Gone(503))
        subscription = _subscription(reader)

        assert send_push(subscription, {"title": "hi"}) is False
        assert PushSubscription.objects.filter(pk=subscription.pk).exists() is True

    def test_alerts_push_does_not_send_without_keys(self, reader, mocker, settings):
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


def _device(reader, token="fcm-token-1", platform="android"):
    """Store and return one phone."""
    return NativePushDevice.objects.create(user=reader, token=token, platform=platform)


class _Reply:
    """A `requests.Response` as far as the sender reads one."""

    def __init__(self, status, body=None):
        self.status_code = status
        self.ok = status < 400
        self._body = body
        self.text = str(body)

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


class TestAlertsNativePushConfigured:
    """Testing class for whether this deployment can send through FCM."""

    @pytest.mark.parametrize(
        "project,path,expected",
        [("p", "/f.json", True), ("", "/f.json", False), ("p", "", False)],
    )
    def test_alerts_push_native_needs_project_and_credentials(
        self, settings, project, path, expected
    ):
        settings.FCM_PROJECT_ID = project
        settings.FCM_CREDENTIALS_FILE = path

        assert native_push_configured() is expected


@pytest.mark.django_db
class TestAlertsSendNativePush:
    """Testing class for one send to a phone."""

    @pytest.fixture(autouse=True)
    def _fcm(self, settings, mocker):
        settings.FCM_PROJECT_ID = "proj"
        settings.FCM_CREDENTIALS_FILE = "/f.json"
        mocker.patch.object(push, "_access_token", return_value="tok")

    def test_alerts_push_native_posts_to_the_project_with_a_bearer(self, reader, mocker):
        post = mocker.patch("requests.post", return_value=_Reply(200, {}))

        assert send_native_push(_device(reader), {"title": "t"}) is True
        assert post.call_args.args[0].endswith("/projects/proj/messages:send")
        assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer tok"}

    def test_alerts_push_native_message_carries_text_url_and_tag(self, reader, mocker):
        post = mocker.patch("requests.post", return_value=_Reply(200, {}))
        payload = {"title": "ASA Stats", "body": "b", "url": "/x", "tag": "alert-3"}

        send_native_push(_device(reader), payload)

        message = post.call_args.kwargs["json"]["message"]
        assert message["token"] == "fcm-token-1"
        assert message["notification"] == {"title": "ASA Stats", "body": "b"}
        assert message["data"] == {"url": "/x"}
        assert message["android"]["notification"]["tag"] == "alert-3"
        assert message["apns"]["headers"]["apns-collapse-id"] == "alert-3"

    def test_alerts_push_native_deletes_an_unregistered_token(self, reader, mocker):
        body = {"error": {"details": [{"errorCode": "UNREGISTERED"}]}}
        mocker.patch("requests.post", return_value=_Reply(404, body))
        device = _device(reader)

        assert send_native_push(device, {"title": "t"}) is False
        assert NativePushDevice.objects.filter(pk=device.pk).exists() is False

    def test_alerts_push_native_deletes_on_unregistered_detail_without_404(
        self, reader, mocker
    ):
        body = {"error": {"details": [{"errorCode": "UNREGISTERED"}]}}
        mocker.patch("requests.post", return_value=_Reply(400, body))
        device = _device(reader)

        assert send_native_push(device, {"title": "t"}) is False
        assert NativePushDevice.objects.filter(pk=device.pk).exists() is False

    @pytest.mark.parametrize("status", [401, 429, 500, 503])
    def test_alerts_push_native_keeps_a_token_that_merely_failed(
        self, reader, mocker, status
    ):
        mocker.patch("requests.post", return_value=_Reply(status))
        device = _device(reader)

        assert send_native_push(device, {"title": "t"}) is False
        assert NativePushDevice.objects.filter(pk=device.pk).exists() is True

    def test_alerts_push_native_survives_a_network_error(self, reader, mocker):
        mocker.patch("requests.post", side_effect=OSError("down"))
        device = _device(reader)

        assert send_native_push(device, {"title": "t"}) is False
        assert NativePushDevice.objects.filter(pk=device.pk).exists() is True

    def test_alerts_push_native_survives_a_credentials_error(self, reader, mocker):
        mocker.patch.object(push, "_access_token", side_effect=ValueError("bad key"))
        post = mocker.patch("requests.post")

        assert send_native_push(_device(reader), {"title": "t"}) is False
        assert post.called is False

    def test_alerts_push_native_does_not_send_unconfigured(self, reader, mocker, settings):
        settings.FCM_PROJECT_ID = ""
        post = mocker.patch("requests.post")

        assert send_native_push(_device(reader), {"title": "t"}) is False
        assert post.called is False


class TestAlertsAccessToken:
    """Testing class for the cached FCM credentials."""

    @pytest.fixture(autouse=True)
    def _reset(self, settings, mocker):
        settings.FCM_CREDENTIALS_FILE = "/f.json"
        mocker.patch.object(push, "_credentials", None)

    def test_alerts_push_token_loads_once_and_refreshes_only_when_invalid(self, mocker):
        credentials = mocker.MagicMock(valid=False, token="abc")
        load = mocker.patch(
            "google.oauth2.service_account.Credentials.from_service_account_file",
            return_value=credentials,
        )
        mocker.patch("google.auth.transport.requests.Request")

        assert push._access_token() == "abc"
        credentials.valid = True
        push._access_token()

        assert load.call_count == 1
        assert credentials.refresh.call_count == 1


@pytest.mark.django_db
class TestAlertsNotifyBoth:
    """Testing class for the fan-out over browsers and phones."""

    def test_alerts_push_notify_counts_browsers_and_phones(self, reader, mocker):
        _subscription(reader)
        _device(reader)
        _device(reader, token="fcm-token-2", platform="ios")
        mocker.patch.object(push, "send_push", return_value=True)
        mocker.patch.object(push, "send_native_push", return_value=True)

        assert notify(reader, {"title": "hi"}) == 3

    def test_alerts_push_notify_does_not_count_a_failed_phone(self, reader, mocker):
        _device(reader)
        mocker.patch.object(push, "send_native_push", return_value=False)

        assert notify(reader, {"title": "hi"}) == 0

    def test_alerts_push_notify_reaches_phones_without_vapid_keys(
        self, reader, mocker, settings
    ):
        """A deployment with FCM and no VAPID keys still notifies phones."""
        settings.VAPID_PRIVATE_KEY = ""
        _device(reader)
        sent = mocker.patch.object(push, "send_native_push", return_value=True)

        assert notify(reader, {"title": "hi"}) == 1
        assert sent.called

"""Sending a web push, and knowing when to stop.

**This is the whole of the website's delivery half.** The background work -
deciding that a rule fired - belongs in the engine, beside the historic
pipeline's own huey tasks; see `notifications/DESIGN.md`. What is left here is
one HTTPS request to a push service, which is a function call rather than
something to queue.

**A push is encrypted for one browser.** The subscription carries the endpoint
and the client's half of the keys; `pywebpush` does the encryption and signs the
request with our VAPID private key so the service knows who is asking.
"""

import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

#: Push services answer these for an endpoint that no longer exists.
#:
#: **Delete rather than retry.** A cleared profile or an uninstalled PWA leaves a
#: subscription nothing can ever be delivered to, and retrying it turns a normal
#: event into a permanent error in a log nobody reads. 404 is "never heard of
#: it"; 410 is "it was here and is gone". Both mean the same thing to us.
GONE_STATUSES = (404, 410)


#: FCM's HTTP v1 endpoint and the scope its OAuth token is minted for.
FCM_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
FCM_TIMEOUT = 10

#: One credentials object per process, refreshed only when it expires; see
#: `docs/logbook.md` (inhouse/alerts/push.py).
_credentials = None


def push_configured():
    """Whether this deployment has VAPID keys.

    **Absence is a configuration state, not an error.** A fork with no keys
    should still run the site, and the alerts widget should still store rules -
    they simply will not be delivered. Every caller checks this rather than
    discovering it as an exception from inside `pywebpush`.

    :return: Boolean
    """
    return bool(settings.VAPID_PRIVATE_KEY and settings.VAPID_ADMIN_EMAIL)


def send_push(subscription, payload):
    """Send one notification, and report whether the subscription survived.

    :param subscription: the browser to notify
    :type subscription: :class:`widgets.inhouse.alerts.models.PushSubscription`
    :param payload: what the service worker will receive
    :type payload: dict
    :return: True when delivered, False when the subscription is gone or the
        deployment cannot send
    :rtype: bool
    """
    if not push_configured():
        logger.warning("push not configured; %s not sent", payload.get("title"))
        return False

    # **Imported here, not at module scope.** `pywebpush` pulls in aiohttp and
    # its own crypto stack, and a deployment without the package should fail
    # when it tries to send rather than when Django starts.
    from pywebpush import WebPushException, webpush  # noqa: PLC0415

    try:
        webpush(
            subscription_info=subscription.as_dict(),
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_ADMIN_EMAIL},
        )
    except WebPushException as error:
        status = getattr(getattr(error, "response", None), "status_code", None)
        if status in GONE_STATUSES:
            # The browser is not coming back. Info rather than a warning:
            # this is the ordinary end of a subscription's life.
            logger.info("push subscription gone (%s), removing", status)
            subscription.delete()
            return False
        logger.warning("push failed (%s): %s", status, error)
        return False
    return True


def native_push_configured():
    """Whether this deployment can send through FCM.

    :return: Boolean
    """
    return bool(settings.FCM_PROJECT_ID and settings.FCM_CREDENTIALS_FILE)


def _access_token():
    """Return a valid OAuth token for FCM, refreshing the cached one if needed.

    :return: str
    """
    global _credentials  # noqa: PLW0603

    # Lazy, like `pywebpush`: a deployment without `google-auth` fails when it
    # sends, not when Django starts.
    from google.auth.transport.requests import Request  # noqa: PLC0415
    from google.oauth2 import service_account  # noqa: PLC0415

    if _credentials is None:
        _credentials = service_account.Credentials.from_service_account_file(
            settings.FCM_CREDENTIALS_FILE, scopes=[FCM_SCOPE]
        )
    if not _credentials.valid:
        _credentials.refresh(Request())
    return _credentials.token


def _fcm_message(device, payload):
    """Return the FCM request body for one device.

    :param device: the phone to notify
    :type device: :class:`widgets.inhouse.alerts.models.NativePushDevice`
    :param payload: what the web push would carry
    :type payload: dict
    :return: dict
    """
    message = {
        "token": device.token,
        "notification": {
            "title": payload.get("title", ""),
            "body": payload.get("body", ""),
        },
        # FCM data values must be strings; the app opens `url` on a tap.
        "data": {"url": payload.get("url", "")},
    }
    tag = payload.get("tag")
    if tag:
        message["android"] = {"notification": {"tag": tag}}
        message["apns"] = {"headers": {"apns-collapse-id": tag}}
    return {"message": message}


def _token_is_gone(response):
    """Whether FCM says this registration token will never work again.

    :param response: FCM's error response
    :type response: :class:`requests.Response`
    :return: Boolean
    """
    if response.status_code == 404:
        return True
    try:
        details = response.json().get("error", {}).get("details", [])
    except ValueError:
        return False
    return any(detail.get("errorCode") == "UNREGISTERED" for detail in details)


def send_native_push(device, payload):
    """Send one notification to a phone, and report whether the token survived.

    :param device: the phone to notify
    :type device: :class:`widgets.inhouse.alerts.models.NativePushDevice`
    :param payload: the same dict `send_push` takes
    :type payload: dict
    :return: True when delivered, False when the token is gone or it failed
    :rtype: bool
    """
    if not native_push_configured():
        logger.warning("native push not configured; %s not sent", payload.get("title"))
        return False

    try:
        response = requests.post(
            FCM_URL.format(project=settings.FCM_PROJECT_ID),
            headers={"Authorization": f"Bearer {_access_token()}"},
            json=_fcm_message(device, payload),
            timeout=FCM_TIMEOUT,
        )
    except Exception as error:  # noqa: BLE001 - one phone must not stop the rest
        logger.warning("native push failed: %s", error)
        return False

    if response.ok:
        return True
    if _token_is_gone(response):
        logger.info("native push token gone (%s), removing", response.status_code)
        device.delete()
        return False
    logger.warning("native push failed (%s): %s", response.status_code, response.text)
    return False


def notify(user, payload):
    """Notify every browser and every app install `user` has registered.

    **Every row, because a subscription is per browser.** A reader with a laptop
    and a phone has two, and telling only one of them is the bug this function
    exists to not have.

    :param user: the reader to notify
    :param payload: what the service worker will receive
    :type payload: dict
    :return: how many browsers and phones were reached
    :rtype: int
    """
    from .models import NativePushDevice, PushSubscription  # noqa: PLC0415 - cycle

    sent = 0
    for subscription in PushSubscription.objects.filter(user=user):
        if send_push(subscription, payload):
            sent += 1
    for device in NativePushDevice.objects.filter(user=user):
        if send_native_push(device, payload):
            sent += 1
    return sent

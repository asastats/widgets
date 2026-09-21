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

from django.conf import settings

logger = logging.getLogger(__name__)

#: Push services answer these for an endpoint that no longer exists.
#:
#: **Delete rather than retry.** A cleared profile or an uninstalled PWA leaves a
#: subscription nothing can ever be delivered to, and retrying it turns a normal
#: event into a permanent error in a log nobody reads. 404 is "never heard of
#: it"; 410 is "it was here and is gone". Both mean the same thing to us.
GONE_STATUSES = (404, 410)


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
    # its own crypto stack, which is a second of import time this module does
    # not owe to a request that will never send anything - and a deployment
    # without the package should fail when it tries to send, not when Django
    # starts.
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
            # The browser is not coming back to this endpoint. Forget it, and
            # say so at info: this is the ordinary end of a subscription's life,
            # not a fault.
            logger.info("push subscription gone (%s), removing", status)
            subscription.delete()
            return False
        logger.warning("push failed (%s): %s", status, error)
        return False
    return True


def notify(user, payload):
    """Notify every browser `user` has subscribed.

    **Every row, because a subscription is per browser.** A reader with a laptop
    and a phone has two, and telling only one of them is the bug this function
    exists to not have.

    :param user: the reader to notify
    :param payload: what the service worker will receive
    :type payload: dict
    :return: how many browsers were reached
    :rtype: int
    """
    from .models import PushSubscription  # noqa: PLC0415 - avoids a cycle

    sent = 0
    for subscription in PushSubscription.objects.filter(user=user):
        if send_push(subscription, payload):
            sent += 1
    return sent

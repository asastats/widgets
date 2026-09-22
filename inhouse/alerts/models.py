"""The alert rules a reader keeps, and the state that stops them repeating.

`notifications/DESIGN.md` is the design; this is the store it calls for. Two
things about the shape are worth knowing before changing it.

**Indexed by asset, because the evaluator reads it that way.** There are two
evaluators: a per-bundle one riding on the live pass for the subjects that watch
a page's own numbers, and a per-asset one for `asa_price`, which is not
per-reader at all. The second asks "who cares about this asset" once per asset
rather than once per rule, and the same index answers "which assets must be kept
fresh" - `PREREQUISITES.md` item 1 notes those are one question, not two.

**Fire state is in v1 and not after the first complaint.** A rule that fires on
a *level* notifies on every tick while the value sits past the threshold, and an
asset oscillating around one notifies forever. So a rule fires on a *crossing*:
the value is past the threshold in the rule's direction now, and was not last
time. `last_value` is what makes that answerable, and the cooldown covers the
case where it crosses back and forth faster than anyone wants telling.
"""

from django.conf import settings
from django.db import models


class Subject(models.TextChoices):
    """What a rule watches.

    The two `total_*` subjects and `ASA_TOTAL` read numbers the live pass
    already publishes every block. `ASA_PRICE` is the one that needs the price
    history half, and the one the thin-asset problem applies to.
    """

    ASA_PRICE = "asa_price", "Asset price"
    ASA_PRICE_PERCENT = "asa_price_percent", "Asset price, percentage move"
    ASA_AMOUNT = "asa_amount", "How much of an asset I hold"
    ASA_TOTAL = "asa_total", "What my holding of an asset is worth"
    TOTAL_VALUE = "total_value", "Portfolio total"
    TOTAL_PERCENT = "total_percent", "Portfolio total, percentage move"


class Direction(models.TextChoices):
    """Which way the value has to cross the threshold to fire."""

    UP = "up", "Rises above"
    DOWN = "down", "Falls below"


#: Subjects that name a single asset, and so require `asset_id`.
ASSET_SUBJECTS = frozenset(
    {
        Subject.ASA_PRICE,
        Subject.ASA_PRICE_PERCENT,
        Subject.ASA_AMOUNT,
        Subject.ASA_TOTAL,
    }
)

#: Subjects whose threshold is a quantity of the asset rather than money.
#:
#: **`asa_amount` is the one subject with no currency.** "I hold more than
#: 1,000 ASASTATS" is true whatever an ASASTATS is worth, which is the whole
#: point of it: a reader waiting for an allocation wants to know it arrived,
#: not what it was worth when it did. So the ALGO/USD control is hidden for it
#: exactly as it is for a percentage.
AMOUNT_SUBJECTS = frozenset({Subject.ASA_AMOUNT})

#: Subjects a reader may denominate in ALGO or in USD.
#:
#: Everything that is money and not a proportion. A percentage has no currency
#: and an amount is a count of the asset itself.
CURRENCY_SUBJECTS = frozenset(
    {
        Subject.ASA_PRICE,
        Subject.ASA_TOTAL,
        Subject.TOTAL_VALUE,
    }
)

#: Subjects the per-asset evaluator answers, and so the assets the engine's
#: price task must keep fresh.
#:
#: **Not every asset subject.** `ASA_TOTAL` is "my holding of this asset on this
#: page", which the live pass already publishes - an asset named only by those
#: rules must not make the price task fetch anything. These two are the ones
#: that need a price nobody else asked for.
PRICED_SUBJECTS = frozenset({Subject.ASA_PRICE, Subject.ASA_PRICE_PERCENT})

#: Subjects expressed as a percentage move, and so require a window.
PERCENT_SUBJECTS = frozenset(
    {Subject.TOTAL_PERCENT, Subject.ASA_PRICE_PERCENT}
)

#: How long a fired rule stays quiet, unless a tier says otherwise.
#:
#: Fifteen minutes is a starting value, not a measurement. It is long enough
#: that a threshold being brushed repeatedly sends one notification rather than
#: a dozen, and short enough that a genuine second move within the hour is still
#: reported.
DEFAULT_COOLDOWN_SECONDS = 900


class AlertRule(models.Model):
    """One thing a reader has asked to be told about.

    :var AlertRule.user: who to notify
    :var AlertRule.subject: what is watched
    :var AlertRule.asset_id: the asset, for the subjects that name one
    :var AlertRule.address: the bundle or address, for the subjects that need one
    :var AlertRule.direction: which crossing fires it
    :var AlertRule.threshold: the value crossed
    :var AlertRule.window_seconds: the period a percentage move is measured over
    :var AlertRule.last_value: what it saw last, which makes a crossing knowable
    :var AlertRule.last_fired_at: when it last notified, for the cooldown
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="alert_rules",
    )
    # 32 rather than the 16 the first four subjects fitted in: `asa_price_percent`
    # is 17, and a subject name is descriptive by design. The column is a choice
    # field, so the width costs nothing and running out of it again would mean
    # another migration for a name.
    subject = models.CharField(max_length=32, choices=Subject.choices)

    # **Nullable, and validated per subject rather than per column.** A
    # portfolio rule names no asset and an asset rule names no bundle; making
    # either mandatory at the database level would mean two tables for what is
    # one concept to the reader.
    asset_id = models.BigIntegerField(null=True, blank=True)

    #: The asset's unit name as the reader picked it, for the sentence.
    #:
    #: **Denormalised deliberately.** The notification is built server-side, in
    #: the webhook path, where this widget has no asset lookup at all - it is
    #: `capability = "public"` with no engine endpoints, so it cannot ask. The
    #: picker already knows the unit; storing what the reader saw is cheaper
    #: than acquiring the ability to look it up, and it is also the more honest
    #: label: it is the asset they chose, by the name it had when they chose it.
    #:
    #: Blank when a rule was made before this existed, or by a client that did
    #: not send it; `display` falls back to the id.
    asset_unit = models.CharField(max_length=32, blank=True, default="")

    address = models.CharField(max_length=128, blank=True, default="")

    direction = models.CharField(max_length=4, choices=Direction.choices)
    threshold = models.DecimalField(max_digits=30, decimal_places=10)

    #: What the threshold is denominated in: "algo" or "usd".
    #:
    #: **Stored rather than converted away, and that was a defect.** A USD
    #: threshold used to be turned into ALGO at the rate on the day the rule was
    #: written, and the choice discarded - so "tell me above $500" became a
    #: fixed ALGO figure and, once ALGO had moved, fired at a dollar amount the
    #: reader never picked. The conversion now happens on the *reading*, every
    #: time it is taken, so a rule denominated in dollars stays denominated in
    #: dollars.
    #:
    #: A percentage has no currency and an amount is a count of the asset, so
    #: both store "algo" and never consult it. See `CURRENCY_SUBJECTS`.
    threshold_unit = models.CharField(max_length=4, default="algo")

    window_seconds = models.PositiveIntegerField(null=True, blank=True)

    active = models.BooleanField(default=True)
    cooldown_seconds = models.PositiveIntegerField(
        default=DEFAULT_COOLDOWN_SECONDS
    )

    # Fire state. See the module docstring: a crossing, not a level.
    last_value = models.DecimalField(
        max_digits=30, decimal_places=10, null=True, blank=True
    )
    last_fired_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        indexes = [
            # The per-asset evaluator's only query: which active rules name this
            # asset. Also what answers "which assets must be kept fresh".
            models.Index(
                fields=["asset_id", "active"], name="alert_asset_active_idx"
            ),
            # The per-bundle evaluator's: which active rules watch this page.
            models.Index(
                fields=["address", "active"], name="alert_address_active_idx"
            ),
            models.Index(fields=["user", "active"], name="alert_user_active_idx"),
        ]

    def __str__(self):
        """Return a readable description of the rule.

        :return: str
        """
        target = self.asset_id if self.asset_id is not None else self.address
        return (
            f"{self.get_subject_display()} {target} "
            f"{self.get_direction_display().lower()} {self.threshold}"
        )

    @property
    def needs_asset(self):
        """Whether this subject names a single asset.

        :return: Boolean
        """
        return self.subject in ASSET_SUBJECTS

    @property
    def needs_currency(self):
        """Whether this subject's threshold is money the reader may denominate.

        :return: Boolean
        """
        return self.subject in CURRENCY_SUBJECTS

    @property
    def needs_window(self):
        """Whether this subject is a percentage move over a period.

        :return: Boolean
        """
        return self.subject in PERCENT_SUBJECTS

    @property
    def line(self):
        """The number `crossed` compares a reading against.

        **A percentage rule's threshold is unsigned and its reading is not.**
        The reader stores "5" and means "5% down" or "5% up" depending on the
        direction they picked, while the reading is a signed move - so a falling
        rule has to compare against *minus* five. Without this, `down 5` would
        fire the moment the move dropped below positive five, which is to say
        almost always and for the wrong reason.

        Every other subject compares against the threshold as stored: a total or
        a price is already on the same scale the reader typed.

        :return: float
        """
        threshold = float(self.threshold)
        if self.needs_window and self.direction == Direction.DOWN:
            return -threshold
        return threshold

    def crossed(self, value):
        """Whether `value` crosses this rule's line in its direction.

        **A crossing, not a level.** Returning "is it past the threshold" would
        fire on every tick for as long as it stays there, which is the failure
        `notifications/DESIGN.md` calls the one that makes readers turn the
        feature off. A crossing needs the previous reading, so a rule that has
        never seen one cannot have crossed anything - it arms instead.

        :param value: the reading now
        :type value: decimal.Decimal or float
        :return: Boolean
        """
        if self.last_value is None:
            return False
        was, now = float(self.last_value), float(value)
        line = self.line
        if self.direction == Direction.UP:
            return was <= line < now
        return was >= line > now


class PushSubscription(models.Model):
    """One browser a reader has asked to be notified on.

    **Per browser, not per reader.** A push subscription names an endpoint at
    Apple, Google or Mozilla plus the keys to encrypt for it, and a reader with
    a laptop and a phone has two. Notifying "the user" means notifying every row
    they own.

    **It is a credential, not a preference.** `auth` and `p256dh` are the
    client's half of the encryption; anyone holding the endpoint and these keys
    can deliver a notification the browser will accept as ours. They are written
    by the browser and read only by the sender.

    **Gone means gone.** A push service answers 404 or 410 for an endpoint the
    browser has abandoned - a cleared profile, an uninstalled PWA - and the only
    correct response is to delete the row. Retrying is how a dead subscription
    becomes a permanent error in a log nobody reads.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    # The push service's URL for this browser. Unique because the browser
    # re-sends the same one on every visit, and a reader who signs in on a
    # shared machine must replace the row rather than add a second.
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)

    # What the reader was using, for nothing but telling two rows apart in the
    # settings list. Never parsed to decide behaviour - see `alerts.js`, where
    # what a browser can do is asked of the browser.
    user_agent = models.CharField(max_length=300, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        indexes = [
            models.Index(fields=["user"], name="push_user_idx"),
        ]

    def __str__(self):
        """Return a short description of the subscription.

        :return: str
        """
        return f"{self.user} at {self.endpoint[:40]}…"

    def as_dict(self):
        """Return the shape `pywebpush` wants.

        :return: dict
        """
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": self.p256dh, "auth": self.auth},
        }

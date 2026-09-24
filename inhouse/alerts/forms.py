"""Validation for a rule a reader is trying to keep.

**What the reader decides and what the server decides are different lists**, and
the Dust Sweep modal records why that distinction matters: anything the server
could have worked out for itself must not arrive from the browser, because a
value a reader can edit is a value we would then act on.

So the subject, the direction, the threshold and the window come from the form -
they are the rule, and nobody else can know them. The *allowance* does not: how
many rules this reader may keep is read from their profile here, never posted.
"""

from decimal import Decimal

from django import forms

from .models import (
    ASSET_SUBJECTS,
    CURRENCY_SUBJECTS,
    PERCENT_SUBJECTS,
    PRICED_SUBJECTS,
    AlertRule,
    Direction,
    Subject,
)
from .population import publish_assets, publish_page
from .tiers import rules_allowed

#: Windows a percentage rule may be measured over.
#:
#: **A short list rather than a free number**, because the honest answer depends
#: on how often the thing being watched is sampled, and a reader typing "60" has
#: no way to know whether sixty seconds means anything for their asset. These are
#: chosen to sit above the measured sampling gaps - p50 five minutes, p90 68
#: minutes - so the shortest offered has a fair chance of containing two points.
WINDOW_CHOICES = (
    (3600, "1 hour"),
    (21600, "6 hours"),
    (86400, "24 hours"),
    (604800, "7 days"),
)

#: The units a value threshold may be entered in.
#:
#: **Stored in ALGO whichever is chosen**, because ALGO is what the engine
#: compares against: `unit_price` answers "amount of ALGO for one asset" and the
#: pass publishes the page total in ALGO. A dollar figure is derived from those,
#: and is one re-price behind - which is exactly why the alert itself is not.
#:
#: The cost of converting at save rather than at evaluation, said plainly: a
#: rule entered as $0.50 is stored as the ALGO that bought $0.50 *that day*, so
#: if ALGO's own price moves the rule no longer means $0.50. Converting at
#: evaluation would need the unit kept on the row and the ALGO price carried to
#: the evaluator; it is the better design and it is not this one.
UNIT_CHOICES = (("algo", "ALGO"), ("usd", "USD"))

#: The largest percentage move worth offering. Above this a rule is a way of
#: saying "tell me if it collapses", which `down 90` already says.
MAX_PERCENT = Decimal("100")


class AlertRuleForm(forms.Form):
    """One rule, as the modal posts it."""

    subject = forms.ChoiceField(choices=Subject.choices)
    direction = forms.ChoiceField(choices=Direction.choices)
    threshold = forms.DecimalField(max_digits=30, decimal_places=10)
    asset_id = forms.IntegerField(required=False, min_value=0)
    threshold_unit = forms.ChoiceField(
        choices=UNIT_CHOICES, required=False, initial="algo"
    )
    #: The asset's unit name as the picker showed it, posted with the id.
    #:
    #: **Stored rather than looked up**, because the notification is built in
    #: the webhook path where this widget has no asset lookup at all. Optional,
    #: so a client that does not send it still creates a working rule - the
    #: sentence falls back to the id.
    asset_unit = forms.CharField(required=False, max_length=32)
    window_seconds = forms.TypedChoiceField(
        choices=WINDOW_CHOICES, coerce=int, required=False
    )

    def __init__(self, *args, user=None, address="", instance=None, **kwargs):
        """Bind the reader, the page, and the rule being edited if any.

        :param user: the authenticated reader
        :param address: the bundle or address the modal was opened on
        :param instance: the rule being edited, or None when creating
        """
        super().__init__(*args, **kwargs)
        self.user = user
        self.address = address
        self.instance = instance

    def clean_threshold(self):
        """Reject a threshold that cannot mean anything.

        :return: :class:`decimal.Decimal`
        """
        # No try/except: `DecimalField.clean` has already rejected anything
        # that is not a number, so a guard here is a branch no test can reach.
        value = self.cleaned_data["threshold"]
        if value <= 0:
            raise forms.ValidationError("A threshold has to be more than zero.")
        return value

    def clean_threshold_unit(self):
        """Default an absent or empty unit to ALGO.

        The field is optional so that a form posted without it - an older
        cached panel, or a percentage rule where the control is hidden - still
        means what it always meant.

        :return: str
        """
        return self.cleaned_data.get("threshold_unit") or "algo"

    def clean(self):
        """Apply the rules that depend on more than one field.

        **Three checks, and each has a failure it is preventing:**

        an asset subject without an asset is a rule that watches nothing; a
        percentage without a window is a rule whose period is "since we last
        looked", which is not what the label says; and a percentage over 100
        going *down* is a threshold the value can never cross.

        :return: dict
        """
        cleaned = super().clean()
        subject = cleaned.get("subject")
        if not subject:
            return cleaned

        if subject in {s.value for s in ASSET_SUBJECTS}:
            if not cleaned.get("asset_id"):
                self.add_error("asset_id", "Choose an asset to watch.")
        else:
            # Cleared rather than rejected: the modal keeps the field mounted
            # while the reader switches subject, so a leftover value is not the
            # reader's mistake.
            cleaned["asset_id"] = None

        if subject in {s.value for s in PERCENT_SUBJECTS}:
            if not cleaned.get("window_seconds"):
                self.add_error("window_seconds", "Choose a period.")
            threshold = cleaned.get("threshold")
            if threshold is not None and threshold > MAX_PERCENT:
                self.add_error("threshold", "A percentage move cannot be more than 100.")
        else:
            cleaned["window_seconds"] = None

        self._settle_unit(cleaned)
        return cleaned

    def _settle_unit(self, cleaned):
        """Record the currency the reader typed in, without converting.

        **This used to convert, and that was the defect.** A USD threshold was
        turned into ALGO at the rate on the day the rule was written and the
        choice discarded - so "tell me above $500" became a fixed ALGO figure
        which, once ALGO had moved, fired at a dollar amount the reader never
        picked. The conversion now happens on the *reading*, every time one is
        taken; see `evaluate.in_rule_currency`.

        It also converted the wrong way. `algo_usd` held what the engine calls
        `priceusdc`, which is ALGO **per USD** - so a dollar threshold had to be
        multiplied to reach ALGO and was divided instead, by a factor of about
        four each way. Deleting the conversion removes the bug rather than
        correcting it, which is the better of the two outcomes.

        **Only money has a currency.** A percentage and an amount of an asset
        are stored as "algo" and never consult it, so a stale posted value
        cannot turn "5%" into five dollars' worth of anything.

        :param cleaned: the cleaned data, modified in place
        :type cleaned: dict
        """
        subject = cleaned.get("subject")
        if not subject or subject not in {s.value for s in CURRENCY_SUBJECTS}:
            cleaned["threshold_unit"] = "algo"
            return
        cleaned["threshold_unit"] = cleaned.get("threshold_unit") or "algo"

    def clean_subject(self):
        """Refuse a rule the reader's tier does not admit.

        **Checked here rather than in the view**, so that the one place a rule
        is created is the one place the allowance is enforced. A view that
        counted separately would be a second answer to drift from this one.

        :return: str
        """
        subject = self.cleaned_data["subject"]
        profile = getattr(self.user, "profile", None)
        allowed = rules_allowed(getattr(profile, "permission", 0))
        if not allowed:
            raise forms.ValidationError("Alerts are available from the Asastatser tier.")
        # **An edit spends no slot.** The rule being edited is already among
        # the kept ones, so counting it refuses every edit by a reader at their
        # limit - the reader most likely to be changing a rule rather than
        # adding one.
        kept = AlertRule.objects.filter(user=self.user, active=True)
        if self.instance is not None:
            kept = kept.exclude(pk=self.instance.pk)
        kept = kept.count()
        if kept >= allowed:
            raise forms.ValidationError(
                f"That is all {allowed} of your alerts. "
                "Remove one, or upgrade for more."
            )
        return subject

    def save(self):
        """Store the rule, creating one or updating the one being edited.

        **`last_value` is deliberately left unset.** A rule arms on its first
        reading rather than firing on it - see `AlertRule.crossed`. Seeding it
        here with the current value would be the same mistake in a different
        place: the reader would be told about a crossing that happened before
        they asked to be told about anything.

        :return: :class:`AlertRule`
        """
        fields = {
            "subject": self.cleaned_data["subject"],
            "direction": self.cleaned_data["direction"],
            "threshold": self.cleaned_data["threshold"],
            "asset_id": self.cleaned_data.get("asset_id"),
            "asset_unit": self.cleaned_data.get("asset_unit") or "",
            "threshold_unit": self.cleaned_data.get("threshold_unit") or "algo",
            "window_seconds": self.cleaned_data.get("window_seconds"),
            "address": self.address,
        }
        if self.instance is None:
            rule = AlertRule.objects.create(user=self.user, **fields)
        else:
            rule = self.instance
            for name, value in fields.items():
                setattr(rule, name, value)
            # **An edited rule re-arms rather than carrying its old reading.**
            # `last_value` describes a comparison against the *previous*
            # threshold, so keeping it would fire on the difference between two
            # rules rather than on a crossing.
            rule.last_value = None
            rule.last_fired_at = None
            rule.save()
        # **After the row exists, never before**: `publish_page` asks the
        # database what to publish. It returns None rather than raising when
        # Redis is away, because a rule the reader has written must be stored
        # whatever the engine can currently hear.
        publish_page(self.address)
        # The only thing that puts an asset in front of the periodic price
        # task; an `asa_total` rule names an asset too and is answered by the
        # live pass instead.
        #
        # **`PRICED_SUBJECTS` rather than `ASA_PRICE`**: `asa_price_percent`
        # needs the asset priced as well, and its series exists only because
        # that task writes to it. An asset missing from `lvra` means an empty
        # `lvah`, which refuses every reading silently - looking exactly like a
        # rule that has not crossed yet.
        if rule.subject in PRICED_SUBJECTS:
            publish_assets()
        return rule

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
    #: What one ALGO was worth when the form was rendered, posted back with it.
    #:
    #: **From the form rather than fetched again at save**, so the number the
    #: reader saw is the number they are held to. Fetching a fresh rate here
    #: would convert at a price they were never shown.
    algo_usd = forms.DecimalField(
        required=False, max_digits=30, decimal_places=10, min_value=0
    )
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
        # No try/except around the comparison: `DecimalField.clean` has already
        # run and rejected anything that is not a number, so `value` is a
        # `Decimal` and comparing one to zero cannot raise. A guard here would
        # be a branch no test could reach.
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
            # A portfolio rule names no asset. Cleared rather than rejected: the
            # modal keeps the field mounted while the reader switches subject,
            # and refusing a leftover value would be a puzzle rather than a
            # correction.
            cleaned["asset_id"] = None

        if subject in {s.value for s in PERCENT_SUBJECTS}:
            if not cleaned.get("window_seconds"):
                self.add_error("window_seconds", "Choose a period.")
            threshold = cleaned.get("threshold")
            if threshold is not None and threshold > MAX_PERCENT:
                self.add_error(
                    "threshold", "A percentage move cannot be more than 100."
                )
        else:
            cleaned["window_seconds"] = None

        self._to_algo(cleaned)
        return cleaned

    def _to_algo(self, cleaned):
        """Convert a USD threshold into the ALGO the row stores.

        **A percentage is not a currency**, so a percent subject is left alone
        however the unit control was left - the template hides it there, and a
        stale posted value must not turn "5%" into "5 ALGO worth of dollars".

        A USD threshold with no rate is refused rather than stored unconverted:
        storing the dollar figure as though it were ALGO is off by whatever an
        ALGO costs, silently, and the rule would fire at a number the reader
        never chose.

        :param cleaned: the cleaned data, modified in place
        :type cleaned: dict
        """
        subject = cleaned.get("subject")
        threshold = cleaned.get("threshold")
        if not subject or threshold is None:
            return
        if subject in {s.value for s in PERCENT_SUBJECTS}:
            cleaned["threshold_unit"] = "algo"
            return
        if cleaned.get("threshold_unit") != "usd":
            return

        rate = cleaned.get("algo_usd")
        if not rate:
            self.add_error(
                "threshold",
                "The ALGO price is not available right now - enter the "
                "threshold in ALGO.",
            )
            return
        cleaned["threshold"] = threshold / rate

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
            raise forms.ValidationError(
                "Alerts are available from the Asastatser tier."
            )
        # **An edit spends no slot, and this is not a nicety.** The rule being
        # edited is already among the kept ones, so counting it would refuse
        # every edit made by a reader at their limit - the reader most likely
        # to want to change a rule rather than add one, and with no way to see
        # why the form kept saying they were full.
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
            #
            # `last_value` describes a comparison against the *previous*
            # threshold. Keeping it across an edit makes the rule fire on the
            # difference between two rules rather than on a crossing: move a
            # "falls below 100" to 50 while the last reading was 90, and the
            # rule is suddenly on the other side of its own line through no
            # movement at all.
            #
            # So the edited rule behaves like a new one - it arms on its next
            # reading - which is also what the reader means by changing it.
            rule.last_value = None
            rule.last_fired_at = None
            rule.save()
        # **After the row exists, never before.** `publish_page` asks the
        # database what it should publish, so telling the engine first would
        # publish the state that has not happened yet - and it returns None
        # rather than raising when Redis is away, because a rule the reader has
        # written must be stored whatever the engine can currently hear.
        publish_page(self.address)
        # The asset set only changes for a *priced* subject, and this is the
        # only thing that puts an asset in front of the periodic task - an
        # `asa_total` rule names an asset too and is answered by the live pass.
        #
        # `PRICED_SUBJECTS` rather than `ASA_PRICE`: `asa_price_percent` needs
        # the asset priced as well, and more urgently, because its series only
        # exists because the price task writes to it. An asset missing from
        # `lvra` means an empty `lvah`, which means every reading refused -
        # silently, and looking exactly like a rule that has not crossed yet.
        if rule.subject in PRICED_SUBJECTS:
            publish_assets()
        return rule

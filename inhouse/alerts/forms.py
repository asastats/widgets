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
    AlertRule,
    Direction,
    Subject,
)
from .population import publish_page
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

#: The largest percentage move worth offering. Above this a rule is a way of
#: saying "tell me if it collapses", which `down 90` already says.
MAX_PERCENT = Decimal("100")


class AlertRuleForm(forms.Form):
    """One rule, as the modal posts it."""

    subject = forms.ChoiceField(choices=Subject.choices)
    direction = forms.ChoiceField(choices=Direction.choices)
    threshold = forms.DecimalField(max_digits=30, decimal_places=10)
    asset_id = forms.IntegerField(required=False, min_value=0)
    window_seconds = forms.TypedChoiceField(
        choices=WINDOW_CHOICES, coerce=int, required=False
    )

    def __init__(self, *args, user=None, address="", **kwargs):
        """Bind the reader and the page the rule is being made from.

        :param user: the authenticated reader
        :param address: the bundle or address the modal was opened on
        """
        super().__init__(*args, **kwargs)
        self.user = user
        self.address = address

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

        return cleaned

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
        kept = AlertRule.objects.filter(user=self.user, active=True).count()
        if kept >= allowed:
            raise forms.ValidationError(
                f"That is all {allowed} of your alerts. "
                "Remove one, or upgrade for more."
            )
        return subject

    def save(self):
        """Store the rule.

        **`last_value` is deliberately left unset.** A rule arms on its first
        reading rather than firing on it - see `AlertRule.crossed`. Seeding it
        here with the current value would be the same mistake in a different
        place: the reader would be told about a crossing that happened before
        they asked to be told about anything.

        :return: :class:`AlertRule`
        """
        rule = AlertRule.objects.create(
            user=self.user,
            subject=self.cleaned_data["subject"],
            direction=self.cleaned_data["direction"],
            threshold=self.cleaned_data["threshold"],
            asset_id=self.cleaned_data.get("asset_id"),
            window_seconds=self.cleaned_data.get("window_seconds"),
            address=self.address,
        )
        # **After the row exists, never before.** `publish_page` asks the
        # database what it should publish, so telling the engine first would
        # publish the state that has not happened yet - and it returns None
        # rather than raising when Redis is away, because a rule the reader has
        # written must be stored whatever the engine can currently hear.
        publish_page(self.address)
        return rule

"""Form for the reader's own figures in the profit and loss widget."""

import re
from decimal import Decimal

from django import forms

#: A transaction or group id, as the engine accepts it.
OVERRIDE_EVENT = re.compile(r"[A-Za-z0-9+/=_-]{1,64}")


class PnlOverrideForm(forms.Form):
    """A deposit's cost or an asset's value, in one of the reader's currencies.

    :var PnlOverrideForm.amount: what the reader enters, zero or more
    :type PnlOverrideForm.amount: :class:`django.forms.DecimalField`
    :var PnlOverrideForm.currency: the amount's currency
    :type PnlOverrideForm.currency: :class:`django.forms.ChoiceField`
    """

    amount = forms.DecimalField(
        min_value=Decimal(0),
        max_value=Decimal(10) ** 15,
        max_digits=28,
        decimal_places=12,
    )
    currency = forms.ChoiceField()

    def __init__(self, *args, currencies=(), **kwargs):
        """Offer only `currencies`, the reader's own.

        :param currencies: lower-case currency codes the tier offers
        :type currencies: tuple
        """
        super().__init__(*args, **kwargs)
        self.fields["currency"].choices = [(code, code.upper()) for code in currencies]

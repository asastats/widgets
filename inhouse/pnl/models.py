"""Bundles a reader has processed for P&L, so the total address count can be capped."""

from django.conf import settings
from django.db import models


class PnlBundle(models.Model):
    """One bundle a reader keeps in the P&L widget.

    :var PnlBundle.user: reader keeping the bundle
    :type PnlBundle.user: :class:`django.contrib.auth.models.User`
    :var PnlBundle.bundle: bundle hash
    :type PnlBundle.bundle: str
    :var PnlBundle.address_count: number of addresses in the bundle
    :type PnlBundle.address_count: int
    :var PnlBundle.created_at: when the reader first processed it
    :type PnlBundle.created_at: :class:`datetime.datetime`
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pnl_bundles"
    )
    bundle = models.CharField(max_length=58)
    address_count = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "bundle"], name="pnl_user_bundle_uniq"
            )
        ]

    def __str__(self):
        """Return the bundle and its size."""
        return f"{self.bundle} ({self.address_count})"


class PnlSettings(models.Model):
    """A reader's P&L preferences, one row per reader.

    :var PnlSettings.SEPARATORS: CSV separator keys and the characters they stand for
    :type PnlSettings.SEPARATORS: dict
    :var PnlSettings.SEPARATOR_CHOICES: CSV separator keys and their labels
    :type PnlSettings.SEPARATOR_CHOICES: list
    :var PnlSettings.COST_METHOD_CHOICES: cost basis methods and their labels
    :type PnlSettings.COST_METHOD_CHOICES: list
    :var PnlSettings.user: reader the preferences belong to
    :type PnlSettings.user: :class:`django.contrib.auth.models.User`
    :var PnlSettings.csv_separator: key of the CSV export's separator character
    :type PnlSettings.csv_separator: str
    :var PnlSettings.cost_method: cost basis method, as the engine names it
    :type PnlSettings.cost_method: str
    """

    SEPARATORS = {"comma": ",", "semicolon": ";", "tab": "\t"}
    SEPARATOR_CHOICES = [
        ("comma", "Comma (,)"),
        ("semicolon", "Semicolon (;)"),
        ("tab", "Tab"),
    ]
    COST_METHOD_CHOICES = [
        ("average", "Average cost"),
        ("fifo", "FIFO (first in, first out)"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pnl_settings"
    )
    csv_separator = models.CharField(
        max_length=9,
        choices=SEPARATOR_CHOICES,
        default="comma",
    )
    cost_method = models.CharField(
        max_length=7,
        choices=COST_METHOD_CHOICES,
        default="average",
    )

    def __str__(self):
        """Return the reader and the separator."""
        return f"{self.user} ({self.csv_separator})"

    @property
    def separator(self):
        """Return the CSV separator character.

        :return: str
        """
        return self.SEPARATORS[self.csv_separator]

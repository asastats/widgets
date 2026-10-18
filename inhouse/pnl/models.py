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
    :var PnlSettings.PAGE_FORMAT_CHOICES: PDF report page sizes and their labels
    :type PnlSettings.PAGE_FORMAT_CHOICES: list
    :var PnlSettings.user: reader the preferences belong to
    :type PnlSettings.user: :class:`django.contrib.auth.models.User`
    :var PnlSettings.csv_separator: key of the CSV export's separator character
    :type PnlSettings.csv_separator: str
    :var PnlSettings.cost_method: cost basis method, as the engine names it
    :type PnlSettings.cost_method: str
    :var PnlSettings.page_format: PDF report's page size, as the engine names it
    :type PnlSettings.page_format: str
    :var PnlSettings.count_nfts: whether held NFTs are valued at their appraisal
    :type PnlSettings.count_nfts: Boolean
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
        ("lifo", "LIFO (last in, first out)"),
        ("hifo", "HIFO (highest cost out first)"),
    ]
    PAGE_FORMAT_CHOICES = [("a4", "A4"), ("letter", "US Letter")]

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
    page_format = models.CharField(
        max_length=6,
        choices=PAGE_FORMAT_CHOICES,
        default="a4",
    )
    count_nfts = models.BooleanField(default=True)

    def __str__(self):
        """Return the reader and the separator."""
        return f"{self.user} ({self.csv_separator})"

    @property
    def separator(self):
        """Return the CSV separator character.

        :return: str
        """
        return self.SEPARATORS[self.csv_separator]


class PnlHiddenAsset(models.Model):
    """An asset a reader hid from a bundle's table; it still counts in the totals.

    :var PnlHiddenAsset.user: reader who hid it
    :type PnlHiddenAsset.user: :class:`django.contrib.auth.models.User`
    :var PnlHiddenAsset.bundle: bundle hash
    :type PnlHiddenAsset.bundle: str
    :var PnlHiddenAsset.asset: asset id as the engine names it
    :type PnlHiddenAsset.asset: str
    :var PnlHiddenAsset.created_at: when the reader hid it
    :type PnlHiddenAsset.created_at: :class:`datetime.datetime`
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pnl_hidden_assets",
    )
    bundle = models.CharField(max_length=58)
    asset = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "bundle", "asset"], name="pnl_user_bundle_asset_uniq"
            )
        ]

    def __str__(self):
        """Return the bundle and the asset."""
        return f"{self.bundle} {self.asset}"


class PnlOverride(models.Model):
    """The reader's own figure for a bundle: a deposit's cost or an asset's value.

    Sent to the engine with every request; see docs/logbook.md.

    :var PnlOverride.KIND_CHOICES: override kinds and their labels
    :type PnlOverride.KIND_CHOICES: list
    :var PnlOverride.user: reader who set it
    :type PnlOverride.user: :class:`django.contrib.auth.models.User`
    :var PnlOverride.bundle: bundle hash
    :type PnlOverride.bundle: str
    :var PnlOverride.kind: "basis" for a deposit's cost, "value" for an asset's
        value, "own" for another wallet of the reader's
    :type PnlOverride.kind: str
    :var PnlOverride.asset: asset id as the engine names it
    :type PnlOverride.asset: str
    :var PnlOverride.event: the deposit's transaction or group id, or the wallet's
        address; empty for a value
    :type PnlOverride.event: str
    :var PnlOverride.amount: the deposit's whole cost, or the value of one whole unit
    :type PnlOverride.amount: :class:`decimal.Decimal`
    :var PnlOverride.currency: `amount`'s currency, as the engine names it
    :type PnlOverride.currency: str
    :var PnlOverride.created_at: when the reader first set it
    :type PnlOverride.created_at: :class:`datetime.datetime`
    :var PnlOverride.updated_at: when the reader last changed it
    :type PnlOverride.updated_at: :class:`datetime.datetime`
    """

    KIND_CHOICES = [("basis", "Deposit cost"), ("value", "Value"), ("own", "Wallet")]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pnl_overrides"
    )
    bundle = models.CharField(max_length=58)
    kind = models.CharField(max_length=5, choices=KIND_CHOICES)
    asset = models.CharField(max_length=32)
    event = models.CharField(max_length=64, blank=True, default="")
    amount = models.DecimalField(max_digits=28, decimal_places=12)
    currency = models.CharField(max_length=8)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "bundle", "kind", "asset", "event"],
                name="pnl_user_bundle_override_uniq",
            )
        ]

    def __str__(self):
        """Return the bundle, the asset and the figure."""
        return f"{self.bundle} {self.kind} {self.asset} {self.amount} {self.currency}"

    @property
    def amount_text(self):
        """Return the amount without trailing zeros, as the engine reads it.

        :return: str
        """
        return "0" if not self.amount else format(self.amount.normalize(), "f")

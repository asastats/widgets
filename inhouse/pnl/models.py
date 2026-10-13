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
            models.UniqueConstraint(fields=["user", "bundle"], name="pnl_user_bundle_uniq")
        ]

    def __str__(self):
        """Return the bundle and its size."""
        return f"{self.bundle} ({self.address_count})"

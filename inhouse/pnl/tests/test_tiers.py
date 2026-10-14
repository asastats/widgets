"""Testing module for :py:mod:`widgets.inhouse.pnl.tiers` module."""

import pytest

from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS
from widgets.inhouse.pnl.manifest import MANIFEST
from widgets.inhouse.pnl.tiers import features_for, is_subscriber
from widgethost.manifest import addresses_limit_for_permission

ASASTATSER = SUBSCRIPTION_TIER_PERMISSIONS["Asastatser"]


class TestPnlTiers:
    """Testing class for the P&L tier tables."""

    @pytest.mark.parametrize(
        "permission,expected",
        [(None, False), (0, False), (ASASTATSER - 1, False), (ASASTATSER, True)],
    )
    def test_pnl_tiers_is_subscriber(self, permission, expected):
        assert is_subscriber(permission) is expected

    def test_pnl_tiers_features_below_asastatser(self):
        assert features_for(SUBSCRIPTION_TIER_PERMISSIONS["Intro"]) == {
            "linked_only": True,
            "currencies": ("usd",),
            "drilldown": False,
            "periods": ("all",),
            "valuations": ("spot",),
            "chart": False,
            "lp_analytics": False,
        }

    def test_pnl_tiers_features_for_subscribers(self):
        assert features_for(ASASTATSER) == {
            "linked_only": False,
            "currencies": ("usd", "algo"),
            "drilldown": True,
            "periods": ("all", "ytd", "30d", "7d"),
            "valuations": ("spot",),
            "chart": False,
            "lp_analytics": False,
        }

    @pytest.mark.parametrize("tier", ["Professional", "Cluster"])
    def test_pnl_tiers_mve_for_professional_and_up(self, tier):
        assert features_for(SUBSCRIPTION_TIER_PERMISSIONS[tier])["valuations"] == (
            "spot",
            "mve",
        )

    @pytest.mark.parametrize("tier,expected", [("Asastatser", False), ("Professional", True)])
    def test_pnl_tiers_chart_for_professional_and_up(self, tier, expected):
        assert features_for(SUBSCRIPTION_TIER_PERMISSIONS[tier])["chart"] is expected

    def test_pnl_tiers_lp_analytics_for_cluster(self):
        assert (
            features_for(SUBSCRIPTION_TIER_PERMISSIONS["Cluster"])["lp_analytics"] is True
        )

    @pytest.mark.parametrize(
        "tier,expected",
        [("Intro", 1), ("Asastatser", 1), ("Professional", 5), ("Cluster", 20)],
    )
    def test_pnl_tiers_manifest_address_bands(self, tier, expected):
        permission = SUBSCRIPTION_TIER_PERMISSIONS[tier]
        assert (
            addresses_limit_for_permission(MANIFEST.required_permission, permission)
            == expected
        )
        assert addresses_limit_for_permission(MANIFEST.required_permission, 0) == 1

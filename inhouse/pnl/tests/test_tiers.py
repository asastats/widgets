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
            "linked_only": False,
            "currencies": ("usd",),
            "drilldown": False,
            "periods": ("all",),
            "valuations": ("spot",),
            "chart": False,
            "lp_analytics": False,
            "nft_choice": False,
            "export": False,
            "report": False,
            "cost_methods": ("average",),
        }

    @pytest.mark.parametrize(
        "permission,expected",
        [(None, True), (0, True), (SUBSCRIPTION_TIER_PERMISSIONS["Intro"], False)],
    )
    def test_pnl_tiers_linked_only_without_a_subscription(self, permission, expected):
        assert features_for(permission)["linked_only"] is expected

    def test_pnl_tiers_currencies_follow_the_readers_fiat(self):
        intro = SUBSCRIPTION_TIER_PERMISSIONS["Intro"]
        assert features_for(intro, fiat="eur")["currencies"] == ("eur",)
        assert features_for(ASASTATSER, fiat="eur")["currencies"] == ("eur", "algo")

    def test_pnl_tiers_features_for_subscribers(self):
        assert features_for(ASASTATSER) == {
            "linked_only": False,
            "currencies": ("usd", "algo"),
            "drilldown": True,
            "periods": ("all", "ytd", "30d", "7d"),
            "valuations": ("spot",),
            "chart": False,
            "lp_analytics": False,
            "nft_choice": False,
            "export": False,
            "report": False,
            "cost_methods": ("average",),
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

    @pytest.mark.parametrize(
        "tier,expected",
        [("Asastatser", False), ("Professional", True), ("Cluster", True)],
    )
    def test_pnl_tiers_lp_analytics_for_professional_and_up(self, tier, expected):
        assert features_for(SUBSCRIPTION_TIER_PERMISSIONS[tier])["lp_analytics"] is expected

    @pytest.mark.parametrize(
        "tier,expected",
        [("Asastatser", False), ("Professional", True), ("Cluster", True)],
    )
    def test_pnl_tiers_nft_choice_for_professional_and_up(self, tier, expected):
        assert features_for(SUBSCRIPTION_TIER_PERMISSIONS[tier])["nft_choice"] is expected

    @pytest.mark.parametrize(
        "tier,expected",
        [("Professional", ("average",)), ("Cluster", ("average", "fifo", "lifo", "hifo"))],
    )
    def test_pnl_tiers_cost_methods_for_cluster(self, tier, expected):
        assert features_for(SUBSCRIPTION_TIER_PERMISSIONS[tier])["cost_methods"] == expected

    @pytest.mark.parametrize("tier,expected", [("Professional", False), ("Cluster", True)])
    def test_pnl_tiers_export_for_cluster(self, tier, expected):
        assert features_for(SUBSCRIPTION_TIER_PERMISSIONS[tier])["export"] is expected

    @pytest.mark.parametrize("tier,expected", [("Professional", False), ("Cluster", True)])
    def test_pnl_tiers_report_for_cluster(self, tier, expected):
        assert features_for(SUBSCRIPTION_TIER_PERMISSIONS[tier])["report"] is expected

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

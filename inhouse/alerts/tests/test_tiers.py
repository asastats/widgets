"""Testing module for how many alert rules a tier may keep."""

import pytest

from widgets.inhouse.alerts.tiers import (
    ALERT_RULES_PER_TIER,
    more_rules_available,
    rules_allowed,
)
from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS


class TestAlertRulesPerTier:
    """Testing class for the per-tier rule counts."""

    def test_alerts_tiers_table_covers_every_tier(self):
        """**A tier missing from the table would silently allow none.**

        `rules_allowed` falls back to zero for a name it does not find, so a
        tier added to `SUBSCRIPTION_TIER_PERMISSIONS` and forgotten here would
        take alerts away from the readers who pay the most, on a day nobody
        touched this file.
        """
        assert set(SUBSCRIPTION_TIER_PERMISSIONS) <= set(ALERT_RULES_PER_TIER)

    def test_alerts_tiers_are_the_numbers_that_were_set(self):
        """Pinned, because they are a product decision rather than a
        preference: the account holder set them on 2026-09-21."""
        assert ALERT_RULES_PER_TIER == {
            "Trial": 0,
            "Intro": 0,
            "Asastatser": 5,
            "Professional": 25,
            "Cluster": 50,
        }

    @pytest.mark.parametrize(
        ("tier", "expected"),
        [
            ("Intro", 0),
            ("Asastatser", 5),
            ("Professional", 25),
            ("Cluster", 50),
        ],
    )
    def test_alerts_tiers_resolve_a_permission_to_its_band(self, tier, expected):
        assert rules_allowed(SUBSCRIPTION_TIER_PERMISSIONS[tier]) == expected

    def test_alerts_tiers_give_an_unsubscribed_reader_none(self):
        assert rules_allowed(0) == 0

    def test_alerts_tiers_round_a_between_permission_down_not_to_zero(self):
        """**Descending, so an unnamed permission lands on the band below.**

        Permissions are exact tier values today, so nothing produces one
        in between - which is exactly why this is worth a test rather than a
        comment. Answering "none" for a value between two paid tiers would take
        a paying reader's alerts away, and the failure would look like a billing
        bug rather than a lookup one.
        """
        between = (
            SUBSCRIPTION_TIER_PERMISSIONS["Professional"]
            + SUBSCRIPTION_TIER_PERMISSIONS["Cluster"]
        ) // 2

        assert rules_allowed(between) == ALERT_RULES_PER_TIER["Professional"]

    def test_alerts_tiers_admit_more_the_higher_the_tier(self):
        """A ladder that dipped would be a pricing bug, and the table is
        hand-written, so nothing but this notices."""
        ordered = sorted(
            SUBSCRIPTION_TIER_PERMISSIONS.items(), key=lambda item: item[1]
        )
        counts = [ALERT_RULES_PER_TIER[name] for name, _ in ordered]

        assert counts == sorted(counts)

    def test_alerts_tiers_are_not_the_liverefresh_bands(self):
        """**The mistake this project has made twice.**

        `api/tiers.py` records it: two tier axes share tier names, and one has
        twice been derived from the other. The liverefresh widget bands how many
        *addresses* a reader may watch - 1 / 1 / 5 / 20 - and this bands how many
        *rules* they may keep. If these ever become equal by accident, the next
        person to change one will change both.
        """
        watched_addresses = [1, 1, 5, 20]

        assert [
            ALERT_RULES_PER_TIER[name]
            for name in ("Intro", "Asastatser", "Professional", "Cluster")
        ] != watched_addresses


class TestAlertsTiersMoreRulesAvailable:
    """Testing class for whether a capped reader has anywhere to upgrade to."""

    @pytest.mark.parametrize(
        ("tier", "expected"),
        [
            ("Intro", True),
            ("Asastatser", True),
            ("Professional", True),
            ("Cluster", False),
        ],
    )
    def test_alerts_tiers_offer_an_upgrade_below_the_top_band(self, tier, expected):
        permission = SUBSCRIPTION_TIER_PERMISSIONS[tier]

        assert more_rules_available(permission) is expected

    def test_alerts_tiers_offer_an_upgrade_to_an_unsubscribed_reader(self):
        assert more_rules_available(0) is True

    def test_alerts_tiers_read_the_top_from_the_table_not_a_name(self):
        """**Derived, so a band added above `Cluster` needs no change here.**

        Naming the top tier in the upsell would mean two places that have to
        agree about which tier is the top one, and the failure is an invisible
        one: a reader on a new highest band would be shown a link to a plan that
        keeps fewer alerts than the one they already pay for.
        """
        top = max(ALERT_RULES_PER_TIER, key=ALERT_RULES_PER_TIER.get)

        assert more_rules_available(SUBSCRIPTION_TIER_PERMISSIONS[top]) is False

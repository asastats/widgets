"""Testing module for how many alert rules a tier may keep."""

import pytest

from utils.constants.users import SUBSCRIPTION_TIER_PERMISSIONS
from widgets.inhouse.alerts.models import PAGE_SUBJECTS, PRICED_SUBJECTS
from widgets.inhouse.alerts.tiers import (
    ALERT_PAGES_PER_TIER,
    ALERT_RULES_PER_TIER,
    ALERT_SUBJECTS_PER_TIER,
    more_rules_available,
    pages_allowed,
    rules_allowed,
    subjects_allowed,
)


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
        preference. Set 2026-09-21; Trial and Intro opened to price-only rules
        2026-09-27."""
        assert ALERT_RULES_PER_TIER == {
            "Trial": 2,
            "Intro": 5,
            "Asastatser": 5,
            "Professional": 25,
            "Cluster": 50,
        }

    def test_alerts_tiers_pin_the_page_counts_too(self):
        """**The cap that matches the cost**, and the one a rule count cannot
        express: the live pass is charged per page, per block, for ever."""
        assert ALERT_PAGES_PER_TIER == {
            "Trial": 0,
            "Intro": 0,
            "Asastatser": 1,
            "Professional": 5,
            "Cluster": 20,
        }

    @pytest.mark.parametrize(
        ("tier", "expected"),
        [
            ("Intro", 5),
            ("Asastatser", 5),
            ("Professional", 25),
            ("Cluster", 50),
        ],
    )
    def test_alerts_tiers_resolve_a_permission_to_its_band(self, tier, expected):
        assert rules_allowed(SUBSCRIPTION_TIER_PERMISSIONS[tier]) == expected

    def test_alerts_tiers_give_an_unsubscribed_reader_a_pair(self):
        """**Two, and they are price-only.** A feature nobody has seen is hard
        to sell, and a price rule costs nothing per reader - see
        `subjects_allowed` and post-deploy/alerts-tier-analysis.md."""
        assert rules_allowed(0) == 2
        assert pages_allowed(0) == 0

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
        ordered = sorted(SUBSCRIPTION_TIER_PERMISSIONS.items(), key=lambda item: item[1])
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


class TestAlertsTiersSubjects:
    """Testing class for which subjects a tier may watch."""

    def test_alerts_tiers_subject_table_covers_every_tier(self):
        assert set(SUBSCRIPTION_TIER_PERMISSIONS) <= set(ALERT_SUBJECTS_PER_TIER)
        assert set(SUBSCRIPTION_TIER_PERMISSIONS) <= set(ALERT_PAGES_PER_TIER)

    @pytest.mark.parametrize("tier", ("Asastatser", "Professional", "Cluster"))
    def test_alerts_tiers_admit_every_subject_from_asastatser(self, tier):
        allowed = subjects_allowed(SUBSCRIPTION_TIER_PERMISSIONS[tier])

        assert allowed >= {str(s) for s in PRICED_SUBJECTS}
        assert allowed >= {str(s) for s in PAGE_SUBJECTS}

    @pytest.mark.parametrize("permission", (0, SUBSCRIPTION_TIER_PERMISSIONS["Intro"]))
    def test_alerts_tiers_admit_only_priced_subjects_below_that(self, permission):
        """**The gate that makes the cheap tier cheap.** A priced subject is
        answered per asset for every reader at once; every other subject pins a
        page into the live pass. See post-deploy/alerts-tier-analysis.md."""
        assert subjects_allowed(permission) == {str(s) for s in PRICED_SUBJECTS}
        assert pages_allowed(permission) == 0

    def test_alerts_tiers_pages_admit_more_the_higher_the_tier(self):
        """A ladder that dipped would be a pricing bug, and the table is
        hand-written, so nothing but this notices.

        The reasoning for the numbers themselves - why they match the liverefresh
        bands deliberately, and why the two tables stay separate anyway - is in
        the module docstring and in docs/logbook.md.
        """
        ordered = sorted(SUBSCRIPTION_TIER_PERMISSIONS.items(), key=lambda i: i[1])
        counts = [ALERT_PAGES_PER_TIER[name] for name, _ in ordered]

        assert counts == sorted(counts)


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

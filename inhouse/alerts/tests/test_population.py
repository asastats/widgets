"""Testing module for :py:mod:`widgets.inhouse.alerts.population` module."""

import pytest
from django.contrib.auth import get_user_model

from widgets.inhouse.alerts.models import AlertRule, Direction, Subject
from widgets.inhouse.alerts.population import (
    RULE_ASSETS_KEY,
    RULES_KEY,
    publish_assets,
    publish_page,
    published_assets,
    published_pages,
)


@pytest.fixture
def reader(db):
    """Return a user to hang rules on."""
    return get_user_model().objects.create_user(
        username="pop@example.com", email="pop@example.com", password="x"
    )


def _rule(reader, address="BUNDLE", active=True):
    """Store one rule naming `address`."""
    return AlertRule.objects.create(
        user=reader,
        subject=Subject.TOTAL_VALUE,
        direction=Direction.DOWN,
        threshold="100",
        address=address,
        active=active,
    )


@pytest.mark.django_db
class TestAlertsPopulationPublish:
    """Testing class for keeping `lvr` in step with the rules."""

    def test_alerts_population_adds_a_page_that_has_a_rule(self, reader, mocker):
        client = mocker.MagicMock()
        _rule(reader)

        assert publish_page("BUNDLE", client) is True
        key, mapping = client.zadd.call_args.args
        assert key == RULES_KEY
        assert list(mapping) == ["BUNDLE"]

    def test_alerts_population_removes_a_page_with_no_rules(
        self, reader, mocker
    ):
        client = mocker.MagicMock()

        assert publish_page("BUNDLE", client) is False
        client.zrem.assert_called_once_with(RULES_KEY, "BUNDLE")

    def test_alerts_population_keeps_a_page_another_rule_still_names(
        self, reader, mocker
    ):
        """**The reason it is recomputed rather than counted down.** Two rules
        on one page, one deleted: the page must stay, and an incrementing
        membership would have to be told that."""
        client = mocker.MagicMock()
        kept = _rule(reader)
        _rule(reader).delete()

        assert publish_page(kept.address, client) is True
        assert client.zrem.called is False

    def test_alerts_population_ignores_an_inactive_rule(self, reader, mocker):
        """Deactivating is how a reader keeps a rule without spending a slot, so
        it must not keep the page being re-priced either."""
        client = mocker.MagicMock()
        _rule(reader, active=False)

        assert publish_page("BUNDLE", client) is False

    def test_alerts_population_scores_with_a_time_that_never_expires_it(
        self, reader, mocker
    ):
        """**Not heartbeat-scored, unlike the three sets beside it.** The score
        is for whoever reads the set by hand; nothing ages a page out of it,
        because an alert has to outlive the tab that made it.
        """
        client = mocker.MagicMock()
        _rule(reader)

        publish_page("BUNDLE", client)

        _, mapping = client.zadd.call_args.args
        assert isinstance(mapping["BUNDLE"], int)

    def test_alerts_population_ignores_an_empty_address(self, mocker):
        client = mocker.MagicMock()

        assert publish_page("", client) is None
        assert client.zadd.called is False
        assert client.zrem.called is False

    def test_alerts_population_survives_a_redis_that_is_away(
        self, reader, mocker
    ):
        """**A rule the reader has written must be stored** whatever the engine
        can currently hear. The next write repairs the set."""
        client = mocker.MagicMock()
        client.zadd.side_effect = OSError("no route to host")
        _rule(reader)

        assert publish_page("BUNDLE", client) is None

    def test_alerts_population_says_so_in_the_log(self, reader, mocker, caplog):
        client = mocker.MagicMock()
        client.zadd.side_effect = OSError("no route to host")
        _rule(reader)

        publish_page("BUNDLE", client)

        assert "could not publish the alert population" in caplog.text

    def test_alerts_population_makes_its_own_client_when_given_none(
        self, reader, mocker
    ):
        instance = mocker.patch(
            "widgets.inhouse.alerts.population.redis_instance"
        )
        _rule(reader)

        publish_page("BUNDLE")

        assert instance.called


@pytest.mark.django_db
class TestAlertsPopulationRead:
    """Testing class for reading the set back."""

    def test_alerts_population_lists_the_published_pages(self, mocker):
        client = mocker.MagicMock()
        client.zrange.return_value = [b"ONE", b"TWO"]

        assert published_pages(client) == ("ONE", "TWO")

    def test_alerts_population_handles_a_client_that_decodes(self, mocker):
        """Some clients are configured with `decode_responses`, and the members
        arrive as `str`. Both shapes have to read the same."""
        client = mocker.MagicMock()
        client.zrange.return_value = ["ONE"]

        assert published_pages(client) == ("ONE",)

    def test_alerts_population_returns_nothing_when_redis_is_away(self, mocker):
        """It answers the question "which pages are published"; when it cannot
        be asked, an empty answer is honest and a raise is not - this is a
        debugging aid, not a code path anything depends on."""
        client = mocker.MagicMock()
        client.zrange.side_effect = OSError("no route to host")

        assert published_pages(client) == ()


@pytest.mark.django_db
class TestAlertsPopulationAssets:
    """Testing class for keeping `lvra` in step with the price rules."""

    def _price_rule(self, reader, asset_id=31566704, active=True):
        return AlertRule.objects.create(
            user=reader,
            subject=Subject.ASA_PRICE,
            direction=Direction.DOWN,
            threshold="1",
            asset_id=asset_id,
            active=active,
        )

    def test_alerts_population_publishes_a_watched_asset(self, reader, mocker):
        client = mocker.MagicMock()
        self._price_rule(reader)

        assert publish_assets(client) == 1
        key, mapping = client.pipeline.return_value.zadd.call_args.args
        assert key == RULE_ASSETS_KEY
        assert list(mapping) == ["31566704"]

    def test_alerts_population_publishes_asset_ids_as_strings(self, reader, mocker):
        """Redis members are strings either way; doing it here means the engine
        converts back explicitly rather than both sides hoping."""
        client = mocker.MagicMock()
        self._price_rule(reader)

        publish_assets(client)

        _, mapping = client.pipeline.return_value.zadd.call_args.args
        assert all(isinstance(member, str) for member in mapping)

    def test_alerts_population_deduplicates_an_asset(self, reader, mocker):
        """**One question per asset, not per rule.** Two readers watching the
        same asset is the ordinary case, and pricing it twice a run would be
        the per-page mistake in a new place."""
        client = mocker.MagicMock()
        self._price_rule(reader)
        self._price_rule(reader)

        assert publish_assets(client) == 1

    def test_alerts_population_publishes_a_percentage_rules_asset(
        self, reader, mocker
    ):
        """**The subject that cannot be answered without this set.**

        `asa_price_percent` compares an asset's price against its own history,
        and that history exists only because the price task writes a point each
        time it prices the asset. An asset named only by percentage rules and
        left out of `lvra` would never be priced, so the series would stay empty
        and the rule would refuse every reading forever - silently, and looking
        exactly like a rule that has simply not crossed yet.
        """
        client = mocker.MagicMock()
        AlertRule.objects.create(
            user=reader,
            subject=Subject.ASA_PRICE_PERCENT,
            direction=Direction.DOWN,
            threshold="5",
            asset_id=386192725,
            window_seconds=3600,
        )

        assert publish_assets(client) == 1
        _, mapping = client.pipeline.return_value.zadd.call_args.args
        assert list(mapping) == ["386192725"]

    def test_alerts_population_ignores_a_holding_rule(self, reader, mocker):
        """**`asa_total` names an asset too, and must not appear here.** It is
        answered by the live pass out of what it already published, so an asset
        that only ever appears in holding rules would make the price task fetch
        a price nobody asked for."""
        client = mocker.MagicMock()
        AlertRule.objects.create(
            user=reader,
            subject=Subject.ASA_TOTAL,
            direction=Direction.DOWN,
            threshold="1",
            asset_id=31566704,
        )

        assert publish_assets(client) == 0

    def test_alerts_population_ignores_an_inactive_price_rule(self, reader, mocker):
        client = mocker.MagicMock()
        self._price_rule(reader, active=False)

        assert publish_assets(client) == 0

    def test_alerts_population_clears_the_set_when_the_last_rule_goes(
        self, reader, mocker
    ):
        client = mocker.MagicMock()

        assert publish_assets(client) == 0
        client.pipeline.return_value.delete.assert_called_once_with(RULE_ASSETS_KEY)
        assert client.pipeline.return_value.zadd.called is False

    def test_alerts_population_replaces_rather_than_adds(self, reader, mocker):
        """**Rewritten wholesale every time.** There is no per-asset yes/no to
        ask: whether a deleted rule was the last one naming its asset depends on
        every other reader's rules, so the set is recomputed from the database
        and cannot drift."""
        client = mocker.MagicMock()
        self._price_rule(reader)

        publish_assets(client)

        pipeline = client.pipeline.return_value
        assert pipeline.delete.called
        assert pipeline.execute.called

    def test_alerts_population_survives_a_redis_that_is_away(self, reader, mocker):
        client = mocker.MagicMock()
        client.pipeline.return_value.execute.side_effect = OSError("no route")
        self._price_rule(reader)

        assert publish_assets(client) is None

    def test_alerts_population_says_so_in_the_log(self, reader, mocker, caplog):
        client = mocker.MagicMock()
        client.pipeline.return_value.execute.side_effect = OSError("no route")
        self._price_rule(reader)

        publish_assets(client)

        assert "could not publish the alert assets" in caplog.text

    def test_alerts_population_makes_its_own_client_when_given_none(
        self, reader, mocker
    ):
        instance = mocker.patch(
            "widgets.inhouse.alerts.population.redis_instance"
        )

        publish_assets()

        assert instance.called


@pytest.mark.django_db
class TestAlertsPopulationReadAssets:
    """Testing class for reading `lvra` back."""

    def test_alerts_population_lists_the_published_assets(self, mocker):
        client = mocker.MagicMock()
        client.zrange.return_value = [b"1", b"2"]

        assert published_assets(client) == (1, 2)

    def test_alerts_population_handles_a_client_that_decodes(self, mocker):
        client = mocker.MagicMock()
        client.zrange.return_value = ["1"]

        assert published_assets(client) == (1,)

    def test_alerts_population_assets_are_empty_when_redis_is_away(self, mocker):
        client = mocker.MagicMock()
        client.zrange.side_effect = OSError("no route to host")

        assert published_assets(client) == ()

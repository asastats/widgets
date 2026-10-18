"""Testing module for :py:mod:`widgets.inhouse.pnl.models` module."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from widgets.inhouse.pnl.models import (
    PnlBundle,
    PnlHiddenAsset,
    PnlOverride,
    PnlSettings,
)


class TestPnlModelsPnlBundle:
    """Testing class for :py:class:`...pnl.models.PnlBundle`."""

    def test_pnl_models_pnl_bundle_str(self):
        assert str(PnlBundle(bundle="B" * 40, address_count=3)) == f"{'B' * 40} (3)"


class TestPnlModelsPnlSettings:
    """Testing class for :py:class:`...pnl.models.PnlSettings`."""

    def test_pnl_models_pnl_settings_str(self):
        settings = PnlSettings(
            user=get_user_model()(username="reader"), csv_separator="tab"
        )
        assert str(settings) == "reader (tab)"

    def test_pnl_models_pnl_settings_default_separator(self):
        assert PnlSettings().separator == ","

    def test_pnl_models_pnl_settings_separator(self):
        assert [
            PnlSettings(csv_separator=key).separator
            for key, _ in PnlSettings.SEPARATOR_CHOICES
        ] == [",", ";", "\t"]


class TestPnlModelsPnlHiddenAsset:
    """Testing class for :py:class:`...pnl.models.PnlHiddenAsset`."""

    def test_pnl_models_pnl_hidden_asset_str(self):
        assert str(PnlHiddenAsset(bundle="B" * 40, asset="7")) == f"{'B' * 40} 7"


class TestPnlModelsPnlOverride:
    """Testing class for :py:class:`...pnl.models.PnlOverride`."""

    @pytest.mark.parametrize(
        "amount,expected",
        [
            (Decimal("2.500000000000"), "2.5"),
            (Decimal("0E-12"), "0"),
            (Decimal("1E+3"), "1000"),
        ],
    )
    def test_pnl_models_pnl_override_amount_text(self, amount, expected):
        assert PnlOverride(amount=amount).amount_text == expected

    def test_pnl_models_pnl_override_str(self):
        override = PnlOverride(
            bundle="B", kind="value", asset="7", amount=Decimal("2.5"), currency="eur"
        )
        assert str(override) == "B value 7 2.5 eur"

"""Testing module for :py:mod:`widgets.inhouse.folks.views` module."""

import json

from widgets.inhouse.folks.views import (
    FolksAssetsView,
    FolksHoldingsView,
    FolksSwapView,
    _safe_json_for_script,
)


class TestInhouseFolksViewsJsonEscaping:
    # # get_context_data
    def test_inhouse_folks_views_safe_json_for_script_escapes_script_breakout(self):
        # An ASA whose unit tries to break out of the <script> island.
        evil = [
            {
                "id": 1,
                "unit": "</script><img src=x onerror=alert(1)>",
                "name": "x",
                "decimals": 0,
                "amount": "1",
            }
        ]
        out = _safe_json_for_script(evil)
        assert "</script>" not in out
        assert "\\u003c/script\\u003e" in out
        # Round-trips back to the original value (no semantic change).
        assert json.loads(out) == evil


class TestInhouseFolksViewsFolksSwapView:
    """Testing class for :py:class:`widgets.inhouse.folks.views.FolksSwapView`."""

    def test_inhouse_folks_views_folks_swap_view_test_func_resolves_and_gates(
        self, mocker
    ):
        view = FolksSwapView()
        view.args = ["abcdef"]
        resolver = mocker.patch(
            "widgets.inhouse.folks.views.bundle_and_addresses_from_path",
            return_value=("BUNDLEHASH", "ADDR_ONE ADDR_TWO"),
        )
        gate = mocker.patch.object(view, "manifest_test_func", return_value=True)
        assert view.test_func() is True
        resolver.assert_called_once_with("ABCDEF", force_bundle=True)
        gate.assert_called_once_with(2)
        assert view.bundle == "BUNDLEHASH"
        assert view.addresses == "ADDR_ONE ADDR_TWO"

    def test_inhouse_folks_views_folks_swap_view_get_context_data(self, mocker):
        view = FolksSwapView()
        view.request = mocker.MagicMock()
        view.bundle = "BUNDLEHASH"
        view.addresses = "ADDR_ONE ADDR_TWO"
        linked = mocker.patch(
            "widgets.inhouse.folks.views.linked_addresses_for_user",
            return_value={"ADDR_ONE"},
        )
        context = view.get_context_data()
        linked.assert_called_once_with(view.request.user, ["ADDR_ONE", "ADDR_TWO"])
        assert context["bundle"] == "BUNDLEHASH"
        assert context["addresses"] == "ADDR_ONE ADDR_TWO"
        assert context["linked_addresses"] == ["ADDR_ONE"]
        assert context["router_id"] == FolksSwapView.manifest.id
        assert context["folks_network"] == "mainnet"
        assert context["folks_referrer"] == ""
        assert "holdings_json" not in context


class TestInhouseFolksViewsFolksHoldingsView:
    """Testing class for :py:class:`widgets.inhouse.folks.views.FolksHoldingsView`."""

    def test_inhouse_folks_views_folks_holdings_view_test_func_passes(self, mocker):
        view = FolksHoldingsView()
        view.args = ["addr_one"]
        gate = mocker.patch.object(view, "manifest_test_func", return_value=True)
        view.request = mocker.MagicMock()
        linked = mocker.patch(
            "widgets.inhouse.folks.views.is_linked_to_user", return_value=True
        )
        assert view.test_func() is True
        assert view.address == "ADDR_ONE"
        gate.assert_called_once_with(1)
        linked.assert_called_once_with(view.request.user, "ADDR_ONE")

    def test_inhouse_folks_views_folks_holdings_view_test_func_unlinked(self, mocker):
        view = FolksHoldingsView()
        view.args = ["addr_one"]
        mocker.patch.object(view, "manifest_test_func", return_value=True)
        view.request = mocker.MagicMock()
        mocker.patch(
            "widgets.inhouse.folks.views.is_linked_to_user", return_value=False
        )
        assert view.test_func() is False

    def test_inhouse_folks_views_folks_holdings_view_test_func_no_permission(
        self, mocker
    ):
        view = FolksHoldingsView()
        view.args = ["addr_one"]
        mocker.patch.object(view, "manifest_test_func", return_value=False)
        linked = mocker.patch("widgets.inhouse.folks.views.is_linked_to_user")
        assert view.test_func() is False
        linked.assert_not_called()

    def test_inhouse_folks_views_folks_holdings_view_get_context_data(self, mocker):
        import json

        view = FolksHoldingsView()
        view.request = mocker.MagicMock()
        view.address = "ADDR_ONE"
        # Backend returns {asset_id: {name, unit, decimals, amount}} (id 0 = ALGO).
        data = {
            "31566704": {
                "name": "USD Coin",
                "unit": "USDC",
                "decimals": 6,
                "amount": 7,
            },
            "0": {"name": "Algorand", "unit": "ALGO", "decimals": 6, "amount": 5},
        }
        fetch = mocker.patch(
            "widgets.inhouse.folks.views.fetch_account_holdings", return_value=data
        )
        context = view.get_context_data()
        fetch.assert_called_once_with(
            "ADDR_ONE", FolksHoldingsView.manifest.engine_endpoints
        )
        # Flattened, id-sorted, with the id folded in (ALGO first).
        expected = [
            {"name": "Algorand", "unit": "ALGO", "decimals": 6, "amount": 5, "id": 0},
            {
                "name": "USD Coin",
                "unit": "USDC",
                "decimals": 6,
                "amount": 7,
                "id": 31566704,
            },
        ]
        assert context["address"] == "ADDR_ONE"
        assert context["holdings"] == expected
        assert json.loads(context["holdings_json"]) == expected
        assert context["router_id"] == FolksHoldingsView.manifest.id


class TestInhouseFolksViewsFolksAssetsView:
    """Testing class for :py:class:`widgets.inhouse.folks.views.FolksAssetsView`."""

    def test_inhouse_folks_views_folks_assets_view_test_func(self, mocker):
        view = FolksAssetsView()
        gate = mocker.patch.object(view, "manifest_test_func", return_value=True)
        assert view.test_func() is True
        gate.assert_called_once_with(1)

    def test_inhouse_folks_views_folks_assets_view_get_context_data_query(self, mocker):
        view = FolksAssetsView()
        view.request = mocker.MagicMock()
        view.request.GET.get.return_value = "usdc"
        assets = [{"id": 31566704, "unit": "USDC", "name": "USD Coin", "decimals": 6}]
        fetch = mocker.patch(
            "widgets.inhouse.folks.views.fetch_asset_matches", return_value=assets
        )
        context = view.get_context_data()
        fetch.assert_called_once_with("usdc", FolksAssetsView.manifest.engine_endpoints)
        assert context["query"] == "usdc"
        assert context["assets"] == assets

    def test_inhouse_folks_views_folks_assets_view_get_context_data_empty(self, mocker):
        view = FolksAssetsView()
        view.request = mocker.MagicMock()
        view.request.GET.get.return_value = "  "
        fetch = mocker.patch("widgets.inhouse.folks.views.fetch_asset_matches")
        context = view.get_context_data()
        fetch.assert_not_called()
        assert context["query"] == ""
        assert context["assets"] == []

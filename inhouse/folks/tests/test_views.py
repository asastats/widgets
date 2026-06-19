"""Testing module for :py:mod:`widgets.inhouse.folks.views` module."""

from widgets.inhouse.folks.views import (
    ASSETS_PATH,
    HOLDINGS_PATH,
    FolksAssetsView,
    FolksHoldingsView,
    FolksSwapView,
)


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
        assert context["folks_fee_bps"] == 0
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
        view = FolksHoldingsView()
        view.request = mocker.MagicMock()
        view.address = "ADDR_ONE"
        holdings = [{"id": 0, "unit": "ALGO", "decimals": 6, "amount": 5}]
        engine = mocker.patch("widgets.inhouse.folks.views.engine_request")
        engine.return_value.json.return_value = {"holdings": holdings}
        context = view.get_context_data()
        engine.assert_called_once_with(
            "account:holdings",
            "GET",
            HOLDINGS_PATH % "ADDR_ONE",
            FolksHoldingsView.manifest.engine_endpoints,
        )
        assert context["address"] == "ADDR_ONE"
        assert context["holdings"] == holdings
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
        engine = mocker.patch("widgets.inhouse.folks.views.engine_request")
        engine.return_value.json.return_value = {"assets": assets}
        context = view.get_context_data()
        engine.assert_called_once_with(
            "assets:lookup",
            "GET",
            ASSETS_PATH,
            FolksAssetsView.manifest.engine_endpoints,
            params={"q": "usdc"},
        )
        assert context["query"] == "usdc"
        assert context["assets"] == assets

    def test_inhouse_folks_views_folks_assets_view_get_context_data_empty(self, mocker):
        view = FolksAssetsView()
        view.request = mocker.MagicMock()
        view.request.GET.get.return_value = "  "
        engine = mocker.patch("widgets.inhouse.folks.views.engine_request")
        context = view.get_context_data()
        engine.assert_not_called()
        assert context["query"] == ""
        assert context["assets"] == []

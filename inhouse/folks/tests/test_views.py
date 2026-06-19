"""Testing module for :py:mod:`widgets.inhouse.folks.views` module."""

import json

from widgets.inhouse.folks.views import FolksSwapView


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

    def test_inhouse_folks_views_folks_swap_view_get_context_data_injects(
        self, mocker
    ):
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
        assert context["linked_addresses"] == "ADDR_ONE"
        assert context["router_id"] == FolksSwapView.manifest.id
        assert json.loads(context["holdings_json"]) == {"ADDR_ONE": []}
        assert context["folks_network"] == "mainnet"
        assert context["folks_referrer"] == ""
        assert context["folks_fee_bps"] == 0

"""Testing module for :py:mod:`widgets.inhouse.asastats.views` module."""

import json

from widgets.inhouse.asastats.views import (
    AsastatsGroupView,
    AsastatsQuoteView,
    AsastatsSwapView,
    _RouterEndpoint,
)


class TestInhouseAsastatsViewsAsastatsSwapView:
    """Testing class for :py:class:`...views.AsastatsSwapView`."""

    def test_inhouse_asastats_views_swap_view_test_func_resolves_and_gates(
        self, mocker
    ):
        view = AsastatsSwapView()
        view.args = ["abcdef"]
        resolver = mocker.patch(
            "widgets.inhouse.asastats.views.bundle_and_addresses_from_path",
            return_value=("BUNDLEHASH", "ADDR_ONE ADDR_TWO"),
        )
        gate = mocker.patch.object(view, "manifest_test_func", return_value=True)
        assert view.test_func() is True
        resolver.assert_called_once_with("ABCDEF", force_bundle=True)
        gate.assert_called_once_with(2)
        assert view.bundle == "BUNDLEHASH"
        assert view.addresses == "ADDR_ONE ADDR_TWO"

    def test_inhouse_asastats_views_swap_view_get_context_data(self, mocker):
        view = AsastatsSwapView()
        view.request = mocker.MagicMock()
        view.bundle = "BUNDLEHASH"
        view.addresses = "ADDR_ONE ADDR_TWO"
        linked = mocker.patch(
            "widgets.inhouse.asastats.views.linked_addresses_for_user",
            return_value={"ADDR_ONE"},
        )
        context = view.get_context_data()
        linked.assert_called_once_with(view.request.user, ["ADDR_ONE", "ADDR_TWO"])
        assert context["bundle"] == "BUNDLEHASH"
        assert context["addresses"] == "ADDR_ONE ADDR_TWO"
        assert context["linked_addresses"] == ["ADDR_ONE"]
        assert context["router_id"] == AsastatsSwapView.manifest.id

    def test_inhouse_asastats_views_swap_view_passes_no_vendor_config(self, mocker):
        """The browser never talks to a router, so there is nothing to hand it.

        Folks and Haystack pass a network, referrer, fee and API key. Anything
        of that sort appearing here would mean a quote parameter had moved
        client-side, where a user could edit it.
        """
        view = AsastatsSwapView()
        view.request = mocker.MagicMock()
        view.bundle = "BUNDLEHASH"
        view.addresses = "ADDR_ONE"
        mocker.patch(
            "widgets.inhouse.asastats.views.linked_addresses_for_user",
            return_value={"ADDR_ONE"},
        )
        context = view.get_context_data()
        for leaked in ("referrer", "fee_bps", "api_key", "network"):
            assert not any(leaked in key for key in context)


class TestInhouseAsastatsViewsRouterEndpoint:
    """Testing class for :py:class:`...views._RouterEndpoint`."""

    def _view(self, mocker, cls=AsastatsQuoteView, body=b'{"amount": "5"}'):
        view = cls()
        view.request = mocker.MagicMock()
        view.request.body = body
        view.address = "ADDR_ONE"
        return view

    def test_inhouse_asastats_views_endpoint_forwards_to_the_engine(self, mocker):
        view = self._view(mocker)
        call = mocker.patch(
            "widgets.inhouse.asastats.views.engine_request",
            return_value={"amount_out": "9"},
        )
        response = view.post(view.request)
        assert json.loads(response.content) == {"amount_out": "9"}
        scope, method, path, allowed = call.call_args.args
        assert scope == "router:quote"
        assert method == "POST"
        assert path == "router/quote/"
        assert "router:quote" in allowed

    def test_inhouse_asastats_views_endpoint_overrides_the_body_address(
        self, mocker
    ):
        """The gated address wins, so a tampered body cannot route for another.

        `test_func` has already checked the query-string address is linked to
        this user; taking the address from the body instead would make that
        check decorative.
        """
        view = self._view(mocker, body=b'{"address": "SOMEONE_ELSE"}')
        call = mocker.patch(
            "widgets.inhouse.asastats.views.engine_request", return_value={}
        )
        view.post(view.request)
        assert call.call_args.kwargs["json"]["address"] == "ADDR_ONE"

    def test_inhouse_asastats_views_endpoint_refuses_malformed_json(self, mocker):
        view = self._view(mocker, body=b"not json")
        call = mocker.patch("widgets.inhouse.asastats.views.engine_request")
        response = view.post(view.request)
        assert response.status_code == 400
        call.assert_not_called()

    def test_inhouse_asastats_views_endpoint_refuses_a_non_object_body(self, mocker):
        view = self._view(mocker, body=b"[1, 2]")
        call = mocker.patch("widgets.inhouse.asastats.views.engine_request")
        response = view.post(view.request)
        assert response.status_code == 400
        call.assert_not_called()

    def test_inhouse_asastats_views_endpoint_needs_an_address(self, mocker):
        view = AsastatsQuoteView()
        view.request = mocker.MagicMock()
        view.request.GET = {}
        assert view.test_func() is False

    def test_inhouse_asastats_views_endpoint_gates_on_linkage(self, mocker):
        view = AsastatsQuoteView()
        view.request = mocker.MagicMock()
        view.request.GET = {"address": "addr_one"}
        mocker.patch.object(view, "manifest_test_func", return_value=True)
        linked = mocker.patch(
            "widgets.inhouse.asastats.views.is_linked_to_user", return_value=False
        )
        assert view.test_func() is False
        linked.assert_called_once_with(view.request.user, "ADDR_ONE")

    def test_inhouse_asastats_views_group_endpoint_uses_its_own_scope(self, mocker):
        view = self._view(mocker, cls=AsastatsGroupView)
        call = mocker.patch(
            "widgets.inhouse.asastats.views.engine_request", return_value={}
        )
        view.post(view.request)
        scope, _, path, _ = call.call_args.args
        assert scope == "router:group"
        assert path == "router/group/"

    def test_inhouse_asastats_views_both_endpoints_are_gated_the_same_way(self):
        """The group endpoint spends assets; it must not be the laxer of the two."""
        assert AsastatsQuoteView.test_func is _RouterEndpoint.test_func
        assert AsastatsGroupView.test_func is _RouterEndpoint.test_func

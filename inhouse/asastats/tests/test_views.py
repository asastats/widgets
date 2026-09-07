"""Testing module for :py:mod:`widgets.inhouse.asastats.views` module."""

import json

from api.client import BackendError
from django.contrib.auth.models import AnonymousUser
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
        # A real user, not the MagicMock: `post` now resolves this reader's
        # linked addresses for the fee tier, and a mock answers
        # `is_authenticated` truthily and then reaches the ORM with itself as
        # the filter value. Anonymous keeps the forwarding tests off the
        # database; the tests that are *about* the tier patch the resolver.
        view.request.user = AnonymousUser()
        return view

    def _answers(self, mocker, payload):
        """Patch `engine_request` to answer the way it really answers.

        It returns the `requests.Response`, **not** a decoded body. Mocking it
        with a plain dict is what hid a real bug for the life of this widget:
        the view passed the response object straight to `JsonResponse` with no
        `.json()`, every call 500'd, and all of these tests passed anyway
        because the mock had a shape the real function never had. A mock is a
        claim about a contract, and this one was false.
        """
        answer = mocker.MagicMock()
        answer.json.return_value = payload
        return mocker.patch(
            "widgets.inhouse.asastats.views.engine_request", return_value=answer
        )

    def test_inhouse_asastats_views_endpoint_forwards_to_the_engine(self, mocker):
        view = self._view(mocker)
        call = self._answers(mocker, {"amount_out": "9"})
        response = view.post(view.request)
        assert json.loads(response.content) == {"amount_out": "9"}
        scope, method, path, allowed = call.call_args.args
        assert scope == "router:quote"
        assert method == "POST"
        assert path == "/api/v2/internal/router/quote/"
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
        call = self._answers(mocker, {})
        view.post(view.request)
        assert call.call_args.kwargs["json"]["address"] == "ADDR_ONE"

    def test_inhouse_asastats_views_endpoint_sends_the_users_linked_addresses(
        self, mocker
    ):
        """The fee tier's only input, and this is the only layer that knows it.

        The engine authenticates a *deployment*, not a reader, so unless this
        names them nothing can judge a tier. It did not until 2026-09-07, and
        the engine's own reader was an attribute nothing assigned, so the
        published discount table was never granted to anyone.
        """
        view = self._view(mocker)
        call = self._answers(mocker, {})
        mocker.patch(
            "widgets.inhouse.asastats.views.algorand_addresses_for_user",
            return_value={"ADDR_TWO", "ADDR_ONE"},
        )
        view.post(view.request)
        # sorted, so the engine sees a stable list rather than set ordering
        assert call.call_args.kwargs["json"]["linked_addresses"] == [
            "ADDR_ONE",
            "ADDR_TWO",
        ]

    def test_inhouse_asastats_views_endpoint_overrides_body_linked_addresses(
        self, mocker
    ):
        """A page cannot claim a whale's tier by editing the request.

        Same rule as ``address`` and for the same reason: what the browser sent
        is discarded, and the value comes from this user's own rows.
        """
        view = self._view(mocker, body=b'{"linked_addresses": ["A_WHALE"]}')
        call = self._answers(mocker, {})
        mocker.patch(
            "widgets.inhouse.asastats.views.algorand_addresses_for_user",
            return_value={"ADDR_ONE"},
        )
        view.post(view.request)
        assert call.call_args.kwargs["json"]["linked_addresses"] == ["ADDR_ONE"]

    def test_inhouse_asastats_views_endpoint_sends_none_for_an_unlinked_reader(
        self, mocker
    ):
        """An empty list earns zero, which is the full rate - never an error."""
        view = self._view(mocker)
        call = self._answers(mocker, {})
        mocker.patch(
            "widgets.inhouse.asastats.views.algorand_addresses_for_user",
            return_value=set(),
        )
        view.post(view.request)
        assert call.call_args.kwargs["json"]["linked_addresses"] == []

    def test_inhouse_asastats_views_group_endpoint_sends_them_too(self, mocker):
        """Both halves, or the group is built at a rate the quote did not show.

        `quote` prices with the discount and `group` mints the voucher that
        makes the chain honour it. Sending the addresses to one and not the
        other is the quoted-versus-delivered gap `honoured_discount` exists to
        close, reintroduced one layer up.
        """
        view = self._view(mocker, cls=AsastatsGroupView)
        call = self._answers(mocker, {})
        mocker.patch(
            "widgets.inhouse.asastats.views.algorand_addresses_for_user",
            return_value={"ADDR_ONE"},
        )
        view.post(view.request)
        assert call.call_args.kwargs["json"]["linked_addresses"] == ["ADDR_ONE"]

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
        call = self._answers(mocker, {})
        view.post(view.request)
        scope, _, path, _ = call.call_args.args
        assert scope == "router:group"
        assert path == "/api/v2/internal/router/group/"

    def test_inhouse_asastats_views_both_endpoints_are_gated_the_same_way(self):
        """The group endpoint spends assets; it must not be the laxer of the two."""
        assert AsastatsQuoteView.test_func is _RouterEndpoint.test_func
        assert AsastatsGroupView.test_func is _RouterEndpoint.test_func

    def test_inhouse_asastats_views_endpoint_passes_a_refusal_through(self, mocker):
        """The engine's status and its sentence both reach the caller.

        A restricted deployment answers 503 explaining that no group can be
        built for anyone. Letting `BackendError` escape turned that into a 500
        and a stack trace, so the reader saw a crash where there was a reason.
        """
        view = self._view(mocker, cls=AsastatsGroupView)
        mocker.patch(
            "widgets.inhouse.asastats.views.engine_request",
            side_effect=BackendError(
                "503: ...", status_code=503, detail="RESTRICT_TO_ADMIN, so no group"
            ),
        )
        response = view.post(view.request)
        assert response.status_code == 503
        assert json.loads(response.content) == {
            "error": "RESTRICT_TO_ADMIN, so no group"
        }

    def test_inhouse_asastats_views_endpoint_refusal_without_a_detail(self, mocker):
        """A backend that answers with no JSON body still gets a usable status.

        `detail` is None whenever the response would not decode, so the message
        falls back rather than rendering "null" to the reader.
        """
        view = self._view(mocker)
        mocker.patch(
            "widgets.inhouse.asastats.views.engine_request",
            side_effect=BackendError("500: <html>", status_code=500),
        )
        response = view.post(view.request)
        assert response.status_code == 500
        assert json.loads(response.content) == {"error": "the router is unavailable"}

    def test_inhouse_asastats_views_endpoint_refusal_without_a_status(self, mocker):
        """An error carrying no status is reported as a bad gateway, not a 200.

        `BackendError` is raised in one place today, but the default matters:
        `status=None` would make Django answer 200 with an error body, which is
        the one outcome the adapter cannot detect.
        """
        view = self._view(mocker)
        mocker.patch(
            "widgets.inhouse.asastats.views.engine_request",
            side_effect=BackendError("boom"),
        )
        response = view.post(view.request)
        assert response.status_code == 502

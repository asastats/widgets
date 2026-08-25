"""Testing module for :py:mod:`widgets.inhouse.dustsweep.views` module."""

import json

from api.client import BackendError
from widgets.inhouse.dustsweep.views import (
    SWEEP_PATH,
    DustSweepPlanView,
    DustSweepView,
)


class TestInhouseDustsweepViewsDustSweepView:
    """Testing class for :py:class:`...views.DustSweepView`."""

    def test_inhouse_dustsweep_views_sweep_view_test_func_resolves_and_gates(
        self, mocker
    ):
        view = DustSweepView()
        view.args = ["abcdef"]
        resolver = mocker.patch(
            "widgets.inhouse.dustsweep.views.bundle_and_addresses_from_path",
            return_value=("BUNDLEHASH", "ADDR_ONE ADDR_TWO"),
        )
        gate = mocker.patch.object(view, "manifest_test_func", return_value=True)
        assert view.test_func() is True
        resolver.assert_called_once_with("ABCDEF", force_bundle=True)
        gate.assert_called_once_with(2)
        assert view.bundle == "BUNDLEHASH"
        assert view.addresses == "ADDR_ONE ADDR_TWO"

    def test_inhouse_dustsweep_views_sweep_view_get_context_data(self, mocker):
        view = DustSweepView()
        view.request = mocker.MagicMock()
        view.bundle = "BUNDLEHASH"
        view.addresses = "ADDR_ONE ADDR_TWO"
        linked = mocker.patch(
            "widgets.inhouse.dustsweep.views.linked_addresses_for_user",
            return_value={"ADDR_ONE"},
        )
        context = view.get_context_data()
        linked.assert_called_once_with(view.request.user, ["ADDR_ONE", "ADDR_TWO"])
        assert context["bundle"] == "BUNDLEHASH"
        assert context["addresses"] == "ADDR_ONE ADDR_TWO"
        assert context["linked_addresses"] == ["ADDR_ONE"]
        assert context["widget_id"] == DustSweepView.manifest.id

    def test_inhouse_dustsweep_views_sweep_view_renders_only_linked_addresses(
        self, mocker
    ):
        """A sweep needs a signature, so an unlinked address has nothing to offer.

        The context is what the template loops over, so an address that is not
        the user's must not reach it - rendering a panel it could never use
        would invite a bug report rather than a sweep.
        """
        view = DustSweepView()
        view.request = mocker.MagicMock()
        view.bundle = "BUNDLEHASH"
        view.addresses = "ADDR_ONE ADDR_TWO"
        mocker.patch(
            "widgets.inhouse.dustsweep.views.linked_addresses_for_user",
            return_value={"ADDR_TWO"},
        )
        assert view.get_context_data()["linked_addresses"] == ["ADDR_TWO"]

    def test_inhouse_dustsweep_views_sweep_view_passes_no_sweep_parameters(
        self, mocker
    ):
        """Nothing a sweep decides on is handed to the browser.

        No threshold, no fee, no asset list, no creator addresses. Every one of
        those is a decision the engine makes against live state, and any of them
        appearing here would be a value a user could edit into something the
        server then acted on.
        """
        view = DustSweepView()
        view.request = mocker.MagicMock()
        view.bundle = "BUNDLEHASH"
        view.addresses = "ADDR_ONE"
        mocker.patch(
            "widgets.inhouse.dustsweep.views.linked_addresses_for_user",
            return_value={"ADDR_ONE"},
        )
        context = view.get_context_data()
        for leaked in ("threshold", "fee", "creator", "forfeit", "opted"):
            assert not any(leaked in key for key in context)


class TestInhouseDustsweepViewsDustSweepPlanView:
    """Testing class for :py:class:`...views.DustSweepPlanView`."""

    def _view(self, mocker, body=b'{"threshold_algo": 1}'):
        view = DustSweepPlanView()
        view.request = mocker.MagicMock()
        view.request.body = body
        view.address = "ADDR_ONE"
        return view

    def _answers(self, mocker, payload):
        """Patch `engine_request` to answer the way it really answers.

        It returns the `requests.Response`, **not** a decoded body. Mocking it
        with a plain dict is what hid a real bug for the whole life of the
        asastats widget: the view handed the response object straight to
        `JsonResponse` with no `.json()`, so every call 500'd while its tests
        stayed green. A mock is a claim about a contract, and that one was false.
        """
        answer = mocker.MagicMock()
        answer.json.return_value = payload
        return mocker.patch(
            "widgets.inhouse.dustsweep.views.engine_request", return_value=answer
        )

    def test_inhouse_dustsweep_views_plan_forwards_to_the_engine(self, mocker):
        view = self._view(mocker)
        call = self._answers(mocker, {"next": None, "summary": {}})
        response = view.post(view.request)
        assert json.loads(response.content) == {"next": None, "summary": {}}
        scope, method, path, allowed = call.call_args.args
        assert scope == "router:sweep"
        assert method == "POST"
        assert path == SWEEP_PATH
        assert "router:sweep" in allowed

    def test_inhouse_dustsweep_views_plan_uses_an_absolute_engine_path(self):
        """A relative path concatenates into `http://host:8001router/sweep/`.

        `api.client._request` refuses one now, but the refusal is a 502 rather
        than a route - so the path is pinned here too, where the mistake would
        actually be made.
        """
        assert SWEEP_PATH.startswith("/api/v2/")

    def test_inhouse_dustsweep_views_plan_overrides_the_body_address(self, mocker):
        """The gated address wins, so a tampered body cannot sweep another.

        Stronger here than on a swap: this endpoint returns a group that closes
        holdings out, so accepting the body's address would hand any logged-in
        user a way to enumerate and empty an account they do not control.
        """
        view = self._view(mocker, body=b'{"address": "SOMEONE_ELSE"}')
        call = self._answers(mocker, {})
        view.post(view.request)
        assert call.call_args.kwargs["json"]["address"] == "ADDR_ONE"

    def test_inhouse_dustsweep_views_plan_passes_opted_in_through(self, mocker):
        """The one field that widens a sweep, so it must reach the engine intact.

        It is validated there, not here - the widget has no way to know whether
        an asset could be valued.
        """
        view = self._view(mocker, body=b'{"opted_in": [7, 9]}')
        call = self._answers(mocker, {})
        view.post(view.request)
        assert call.call_args.kwargs["json"]["opted_in"] == [7, 9]

    def test_inhouse_dustsweep_views_plan_refuses_malformed_json(self, mocker):
        view = self._view(mocker, body=b"not json")
        call = mocker.patch("widgets.inhouse.dustsweep.views.engine_request")
        response = view.post(view.request)
        assert response.status_code == 400
        call.assert_not_called()

    def test_inhouse_dustsweep_views_plan_refuses_a_non_object_body(self, mocker):
        view = self._view(mocker, body=b"[1, 2]")
        call = mocker.patch("widgets.inhouse.dustsweep.views.engine_request")
        response = view.post(view.request)
        assert response.status_code == 400
        call.assert_not_called()

    def test_inhouse_dustsweep_views_plan_handles_an_empty_body(self, mocker):
        """The controller's first call sends nothing but the address."""
        view = self._view(mocker, body=b"")
        call = self._answers(mocker, {})
        view.post(view.request)
        assert call.call_args.kwargs["json"] == {"address": "ADDR_ONE"}

    def test_inhouse_dustsweep_views_plan_needs_an_address(self, mocker):
        view = DustSweepPlanView()
        view.request = mocker.MagicMock()
        view.request.GET = {}
        assert view.test_func() is False

    def test_inhouse_dustsweep_views_plan_gates_on_linkage(self, mocker):
        view = DustSweepPlanView()
        view.request = mocker.MagicMock()
        view.request.GET = {"address": "addr_one"}
        mocker.patch.object(view, "manifest_test_func", return_value=True)
        linked = mocker.patch(
            "widgets.inhouse.dustsweep.views.is_linked_to_user", return_value=False
        )
        assert view.test_func() is False
        linked.assert_called_once_with(view.request.user, "ADDR_ONE")

    def test_inhouse_dustsweep_views_plan_allows_a_linked_address(self, mocker):
        view = DustSweepPlanView()
        view.request = mocker.MagicMock()
        view.request.GET = {"address": "addr_one"}
        mocker.patch.object(view, "manifest_test_func", return_value=True)
        mocker.patch(
            "widgets.inhouse.dustsweep.views.is_linked_to_user", return_value=True
        )
        assert view.test_func() is True
        assert view.address == "ADDR_ONE"

    def test_inhouse_dustsweep_views_plan_passes_a_refusal_through(self, mocker):
        """The engine's status and its sentence both reach the caller.

        A restricted router answers 503 explaining that no conversion group can
        be built. Letting `BackendError` escape would turn that into a 500 and a
        stack trace, so the reader would see a crash where there is a reason -
        and would not learn that the close-out half still works.
        """
        view = self._view(mocker)
        mocker.patch(
            "widgets.inhouse.dustsweep.views.engine_request",
            side_effect=BackendError(
                "503: ...", status_code=503, detail="RESTRICT_TO_ADMIN, so no group"
            ),
        )
        response = view.post(view.request)
        assert response.status_code == 503
        assert json.loads(response.content) == {
            "error": "RESTRICT_TO_ADMIN, so no group"
        }

    def test_inhouse_dustsweep_views_plan_refusal_without_a_detail(self, mocker):
        view = self._view(mocker)
        mocker.patch(
            "widgets.inhouse.dustsweep.views.engine_request",
            side_effect=BackendError("500: <html>", status_code=500),
        )
        response = view.post(view.request)
        assert response.status_code == 500
        assert json.loads(response.content) == {"error": "the sweep is unavailable"}

    def test_inhouse_dustsweep_views_plan_refusal_without_a_status(self, mocker):
        """An error carrying no status is a bad gateway, not a 200.

        `status=None` would make Django answer 200 with an error body, which is
        the one outcome the controller cannot detect - and it would then loop.
        """
        view = self._view(mocker)
        mocker.patch(
            "widgets.inhouse.dustsweep.views.engine_request",
            side_effect=BackendError("boom"),
        )
        response = view.post(view.request)
        assert response.status_code == 502


class TestInhouseDustsweepManifest:
    """The manifest is what `engine_request` enforces the scopes against."""

    def test_inhouse_dustsweep_manifest_declares_the_sweep_scope(self):
        """A scope the manifest does not name fails closed with a BackendError.

        Which is safe, and indistinguishable from the engine being down unless
        it is asserted.
        """
        assert "router:sweep" in DustSweepView.manifest.engine_endpoints

    def test_inhouse_dustsweep_manifest_is_not_a_swap_router(self):
        """`category = "swap"` would offer the sweep as a default router.

        It is a tool that uses a router, not one - and a profile whose
        `preferred_router` was set to "dustsweep" would have no working swap.
        """
        assert DustSweepView.manifest.category != "swap"
        assert DustSweepView.manifest.id == "dustsweep"

    def test_inhouse_dustsweep_manifest_does_not_reach_beyond_the_sweep(self):
        """Scopes are the engine's gate, so the list is the whole of what we may do."""
        assert set(DustSweepView.manifest.engine_endpoints) == {
            "router:sweep",
            "account:holdings",
            "assets:lookup",
        }

    def test_inhouse_dustsweep_manifest_calls_no_external_host(self):
        """The browser talks only to us; a sweep has no vendor to consult."""
        assert DustSweepView.manifest.hosts == []

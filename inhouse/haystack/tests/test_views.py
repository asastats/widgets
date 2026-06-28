"""Testing module for :py:mod:`widgets.inhouse.haystack.views` module."""

from types import SimpleNamespace

from widgets.inhouse.haystack.views import HaystackSwapView


class TestInhouseHaystackViewsHaystackSwapView:
    """Testing class for :py:class:`widgets.inhouse.haystack.views.HaystackSwapView`."""

    def test_inhouse_haystack_views_haystack_swap_view_attrs(self):
        assert HaystackSwapView.template_name == "haystack/index.html"
        assert HaystackSwapView.manifest.id == "haystack"

    def test_inhouse_haystack_views_haystack_swap_view_client_cfg_context(self, mocker):
        view = HaystackSwapView()
        mocker.patch(
            "widgets.inhouse.haystack.views.settings",
            SimpleNamespace(
                HAYSTACK_REFERRER_ADDRESS="REF_ADDR", HAYSTACK_API_KEY="PUB_KEY"
            ),
        )
        assert view.client_cfg_context() == {
            "haystack_referrer": "REF_ADDR",
            "haystack_api_key": "PUB_KEY",
        }

    def test_inhouse_haystack_views_haystack_swap_view_client_cfg_context_defaults(
        self, mocker
    ):
        view = HaystackSwapView()
        mocker.patch("widgets.inhouse.haystack.views.settings", SimpleNamespace())
        assert view.client_cfg_context() == {
            "haystack_referrer": "",
            "haystack_api_key": "",
        }

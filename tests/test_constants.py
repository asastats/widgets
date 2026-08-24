"""Testing module for :py:mod:`widgets.constants` module."""

from widgets import constants


class TestWidgetsConstants:
    """Testing class for :py:mod:`widgets.constants` module."""

    def test_widgets_constants_inhouse_widgets(self):
        assert constants.INHOUSE_WIDGETS == [
            "historic",
            "folks",
            "haystack",
            "hogswap",
            "asastats",
            "swapcore",
        ]

    def test_widgets_constants_lists_every_swap_router_it_discovers(self):
        """A router discovered by manifest must also be mounted by the list.

        These are two different mechanisms - `widgethost.registry` finds a
        widget by the presence of its `widget.toml`, while `widgets/urls.py`
        mounts only what this list names - and asastats sat in the gap between
        them. It was offered on the settings page and, sorting first, was the
        default for every profile that had never chosen a router, while its
        URLs were never mounted and its entry URL resolved to "".

        Nothing failed loudly, because `swap_entry_url` returns "" when the
        name will not reverse. This is the test that would have.
        """
        import tomllib
        from pathlib import Path

        inhouse = Path(constants.__file__).resolve().parent / "inhouse"
        routers = {
            manifest.parent.name
            for manifest in inhouse.glob("*/widget.toml")
            if tomllib.loads(manifest.read_text()).get("category") == "swap"
        }
        assert routers <= set(constants.INHOUSE_WIDGETS), (
            f"swap routers discovered but not mounted: "
            f"{sorted(routers - set(constants.INHOUSE_WIDGETS))}"
        )

    def test_widgets_constants_thirdparty_widgets(self):
        assert constants.THIRDPARTY_WIDGETS == []

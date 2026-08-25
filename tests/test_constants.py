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
            "dustsweep",
        ]

    def test_widgets_constants_lists_every_widget_it_discovers(self):
        """A widget discovered by manifest must also be mounted by the list.

        These are two different mechanisms - `widgethost.registry` finds a
        widget by the presence of its `widget.toml`, while `widgets/urls.py`
        mounts only what this list names - and asastats sat in the gap between
        them. It was offered on the settings page and, sorting first, was the
        default for every profile that had never chosen a router, while its
        URLs were never mounted and its entry URL resolved to "".

        Nothing failed loudly, because `swap_entry_url` returns "" when the
        name will not reverse. This is the test that would have.

        **Widened from swap routers to every widget on 2026-08-25.** The
        original only globbed for `category = "swap"`, which would have let the
        dust sweep - a tool rather than a router - fall into exactly the same
        gap it was written to close. The gap is about mounting, and mounting
        does not care what category a widget declares.
        """
        import tomllib
        from pathlib import Path

        inhouse = Path(constants.__file__).resolve().parent / "inhouse"
        discovered = {
            manifest.parent.name
            for manifest in inhouse.glob("*/widget.toml")
            if tomllib.loads(manifest.read_text()).get("id")
        }
        assert discovered <= set(constants.INHOUSE_WIDGETS), (
            f"widgets discovered but not mounted: "
            f"{sorted(discovered - set(constants.INHOUSE_WIDGETS))}"
        )

    def test_widgets_constants_names_a_directory_for_every_entry(self):
        """The mirror of the test above: mounted, but nothing there to mount.

        `widgets/urls.py` includes `widgets.inhouse.<name>.urls` for every name
        in the list, so an entry with no directory is an ImportError at startup
        rather than a missing page.
        """
        from pathlib import Path

        inhouse = Path(constants.__file__).resolve().parent / "inhouse"
        missing = [
            widget
            for widget in constants.INHOUSE_WIDGETS
            if not (inhouse / widget / "widget.toml").is_file()
        ]
        assert missing == [], f"mounted but not present: {missing}"

    def test_widgets_constants_thirdparty_widgets(self):
        assert constants.THIRDPARTY_WIDGETS == []

"""Testing module for :py:mod:`widgets.constants` module."""

from widgets import constants


class TestWidgetsConstants:
    """Testing class for :py:mod:`widgets.constants` module."""

    def test_widgets_constants_inhouse_widgets(self):
        assert constants.INHOUSE_WIDGETS == [
            "historic",
            "folks",
            "haystack",
            "swapcore",
        ]

    def test_widgets_constants_thirdparty_widgets(self):
        assert constants.THIRDPARTY_WIDGETS == []

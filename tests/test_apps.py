"""Testing module for core app apps module."""

from django.apps import AppConfig

from widgets.apps import WidgetsConfig


class TestWidgetsApps:
    """Testing class for :py:mod:`widgets.apps` module."""

    # # CoreConfig
    def test_widgets_apps_widgetsconfig_is_subclass_of_appconfig(self):
        assert issubclass(WidgetsConfig, AppConfig)

    def test_widgets_apps_widgetsconfig_sets_name(self):
        assert WidgetsConfig.name == "widgets"

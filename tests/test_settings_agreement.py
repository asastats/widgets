"""Testing module for the two places that list the inhouse widgets.

**There are two, and nothing made them agree until this.** `widgets/constants.py`
is what mounts a widget's URLs and websocket routes; `config/settings/base.py`
keeps its own copy and is what adds the widget's `static/` to
``STATICFILES_DIRS`` and its `templates/` to the template dirs.

A widget added to one and not the other is mounted and unusable, or usable and
unmounted - and neither failure is obvious. Adding `alerts` to the first only,
on 2026-09-21, produced a widget whose views resolved and whose template and
script could not be found: the registry tests passed, the widget suite passed,
and two host tests in a different app caught it.
"""

from django.conf import settings

from widgets.constants import INHOUSE_WIDGETS, THIRDPARTY_WIDGETS


class TestWidgetsSettingsAgreement:
    """Testing class for the duplicated widget lists."""

    def test_widgets_settings_inhouse_lists_agree(self):
        """Same widgets, same order.

        Order matters as much as membership: both lists are iterated to build
        path lists, so a difference in order is a difference in which directory
        wins a name collision.
        """
        assert list(settings.INHOUSE_WIDGETS) == list(INHOUSE_WIDGETS), (
            "config/settings/base.py and widgets/constants.py disagree about "
            "the inhouse widgets. The first adds static/ and templates/ dirs; "
            "the second mounts urls and routing. A widget in one only is "
            "either unusable or unmounted, and neither says so."
        )

    def test_widgets_settings_thirdparty_lists_agree(self):
        assert list(settings.THIRDPARTY_WIDGETS) == list(THIRDPARTY_WIDGETS)

    def test_widgets_settings_every_widget_can_be_found(self):
        """**What the lists are *for*.**

        Agreeing with each other is not enough - they could agree on a widget
        whose directories do not exist. Each mounted widget must have its
        templates reachable, which is what a view needs to render at all.
        """
        from pathlib import Path

        dirs = [Path(d) for d in settings.TEMPLATES[0]["DIRS"]]
        for widget in INHOUSE_WIDGETS:
            expected = Path("widgets") / "inhouse" / widget / "templates"
            assert any(
                str(d).endswith(str(expected)) for d in dirs
            ), f"{widget} is mounted but its templates are not on the path"

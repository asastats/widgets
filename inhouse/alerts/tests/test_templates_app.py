"""The alerts templates in the ASA Stats app: no links towards buying (F10)."""

import pytest
from django.template.loader import render_to_string

from widgets.inhouse.alerts.forms import AlertRuleForm


class _Reader:
    is_authenticated = True


def _render(template, purchase_hidden, **context):
    return render_to_string(
        template, {"PURCHASE_HIDDEN": purchase_hidden, "user": _Reader(), **context}
    )


class TestAlertsTemplatesInApp:
    """Testing class for the alerts templates' upgrade links."""

    def test_alerts_toolbar_without_link_in_app(self):
        html = _render("alerts/_toolbar.html", True, alerts_entitled=False)

        assert "/subscriptions/" not in html
        assert "Asastatser" in html

    def test_alerts_toolbar_links_in_a_browser(self):
        assert "/subscriptions/" in _render(
            "alerts/_toolbar.html", False, alerts_entitled=False
        )

    def test_alerts_modal_without_plans_link_in_app(self):
        html = _render("alerts/modal.html", True, alerts_entitled=False)

        assert "/subscriptions/" not in html
        assert "available from the" in html

    def test_alerts_modal_links_in_a_browser(self):
        assert "See the plans" in _render("alerts/modal.html", False, alerts_entitled=False)

    def _panel(self, purchase_hidden):
        return _render(
            "alerts/_panel.html",
            purchase_hidden,
            form=AlertRuleForm(),
            rules_left=0,
            rules_allowed=5,
            rules_capped=True,
            more_rules_available=True,
            portfolio_alerts_available=False,
        )

    def test_alerts_panel_without_upgrade_in_app(self):
        html = self._panel(True)

        assert "/subscriptions/" not in html
        assert "Upgrade for more" not in html
        assert "Remove one to make room for another." in html
        assert "the limit of your current plan." in html

    def test_alerts_panel_upgrades_in_a_browser(self):
        html = self._panel(False)

        assert "Upgrade for more" in html
        assert "a larger plan" in html

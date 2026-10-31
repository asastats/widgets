"""The P&L templates name only their own hooks, never a CSS framework's classes."""

import re
from pathlib import Path

import pytest

TEMPLATES = sorted((Path(__file__).parents[1] / "templates" / "pnl").glob("*.html"))


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda path: path.name)
def test_pnl_templates_use_only_pnl_classes(template):
    classes = re.findall(r'class="([^"]*)"', template.read_text())
    names = {
        name for value in classes for name in re.sub(r"{[{%].*?[}%]}", " ", value).split()
    }
    assert {name for name in names if not name.startswith("pnl")} == set()


def test_pnl_widget_ships_no_stylesheet():
    assert not list((Path(__file__).parents[1] / "static").rglob("*.css"))


def test_pnl_templates_bundle_addresses_can_wrap():
    """Spaces between the address spans, or a phone cannot break the line."""
    import minify_html
    from django.template import Context, Template

    source = (Path(__file__).parents[1] / "templates" / "pnl" / "index.html").read_text()
    loop = re.search(
        r'<p class="pnl-addresses">.*?</p>', source, re.DOTALL
    ).group(0)
    html = minify_html.minify(
        Template("{% load core_extras %}" + loop).render(
            Context({"addresses": " ".join(c * 58 for c in "ABC")})
        )
    )
    assert "</span> <span" in html
    assert "</span><span" not in html

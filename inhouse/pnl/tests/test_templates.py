"""The P&L templates name only their own hooks, never a CSS framework's classes."""

import re
from pathlib import Path

import pytest

TEMPLATES = sorted((Path(__file__).parents[1] / "templates" / "pnl").glob("*.html"))


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda path: path.name)
def test_pnl_templates_use_only_pnl_classes(template):
    classes = re.findall(r'class="([^"]*)"', template.read_text())
    names = {
        name
        for value in classes
        for name in re.sub(r"{[{%].*?[}%]}", " ", value).split()
    }
    assert {name for name in names if not name.startswith("pnl")} == set()


def test_pnl_widget_ships_no_stylesheet():
    assert not (Path(__file__).parents[1] / "static").exists()

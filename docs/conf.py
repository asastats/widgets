# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import ast
import os
import sys
from unittest.mock import MagicMock

import django
from django.conf import settings
from django.views import View


def get_version():
    init_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "__init__.py"
    )
    with open(init_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=init_path)

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__version__":
                    return ast.literal_eval(node.value)

    raise RuntimeError(f"Unable to find __version__ in {init_path}")


# Two levels, and both are needed.
#
# The widgets package imports flat -- `urls.py` does `from constants import ...`
# and the API sections below are `automodule:: inhouse.<widget>` -- so the
# repository root itself has to be importable. That is `..`, and it was the one
# missing: every `automodule` in widgets.rst raised
# `ModuleNotFoundError: No module named 'inhouse'` and rendered an empty page.
#
# `../..` reaches the frontend's `website/`, which the widgets import from
# (`widgethost`, `core`) and which stays on the path for that reason.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


if not settings.configured:
    settings.configure(
        INSTALLED_APPS=[
            "django.contrib.auth",
            "django.contrib.contenttypes",
            # **The app being documented, and it has to be installed now.**
            # `alerts` is the first in-house widget to keep a table, and a
            # Django model whose app is not installed raises at class-creation
            # time - so importing any module that reaches `alerts.models`
            # failed, which was every path into `widgets.urls`.
            "widgets",
        ],
        DATABASES={
            "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
        },
    )
django.setup()


# --- MOCKING FIX FOR .as_view() AND MRO ---
# Create an empty class for mixins to avoid Python MRO (Method Resolution Order)
# conflicts when inheriting alongside standard Django views like TemplateView.
class DummyMixin:
    pass


class MockSwapViews(MagicMock):
    BaseSwapShellView = View


class MockEnforcement(MagicMock):
    WidgetAccessMixin = DummyMixin


sys.modules["widgethost.swap_views"] = MockSwapViews()
sys.modules["widgethost.enforcement"] = MockEnforcement()
# ------------------------------------------

# -- Project information -----------------------------------------------------

project = "ASA Stats user widgets"
copyright = "2026, ASA Stats DAO"
author = "Ivica Paleka"

release = get_version()

# -- General configuration ---------------------------------------------------

master_doc = "index"

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = ["sphinx.ext.autodoc"]

# Use Sphinx's native mocking to handle the rest of the external dependencies.
autodoc_mock_imports = [
    "api",
    # The host's main app, in the same category as the four beside it and
    # missing from this list until 2026-09-22. A widget importing
    # `core.models.Profile` made Django reject the model - it is neither
    # mocked nor in this build's INSTALLED_APPS - which took `widgets.urls`
    # down with it.
    "core",
    "storage",
    "utils",
    "walletauth",
    "widgethost",
]

# **Two host constants are computed with, not merely named.**
#
# Sphinx's own mock objects do not implement the numeric protocol, so a module
# that does arithmetic on one at import time raises `TypeError` and takes the
# whole importing chain down with it. `inhouse/liverefresh/warmset.py` has
# `WARM_TTL = WARM_SECONDS * 4` at module scope, and that one line is why
# `widgets.urls` - and with it the entire URL configuration page - went
# undocumented behind a single warning.
#
# `MagicMock` does implement the numeric protocol, so these leaf modules get one
# each. It is the same device already used for `widgethost.swap_views` above.
#
# **It has to be a stand-in rather than a real import.** This repository is
# built standalone as well as inside the frontend checkout - there is no `utils`
# package beside it in the former, so importing it crashes `conf.py` outright
# and no documentation is produced at all. `setdefault` keeps the two builds
# behaving identically rather than only one of them working.
for _host_constants in ("utils.constants.core", "utils.constants.users"):
    sys.modules.setdefault(_host_constants, MagicMock())

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "sphinx_rtd_theme"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

html_logo = "_static/logo.png"
html_favicon = "_static/favicon.ico"

latex_documents = [
    (
        "index",
        "asastats-user-widgets.tex",
        "ASA Stats user widgets documentation",
        author,
        "howto",
    )
]

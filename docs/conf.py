# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import sys
# sys.path.insert(0, os.path.abspath('.'))

# from .. import __version__

import os
import sys
from unittest.mock import MagicMock

# import django

sys.path.insert(0, os.path.abspath("../"))

# django.setup()

import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        INSTALLED_APPS=[
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "inhouse.historic",  # your app if it has models
        ],
        DATABASES={
            "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
        },
    )
django.setup()

# Mock external/nonexistent dependencies
MOCK_MODULES = [
    "api",
    "api.data",
    "api.widgets",
    "storage",
    "storage.helpers",
    "storage.ledger",
    "storage.main",
    "utils",
    "utils.charts",
    "utils.constants",
    "utils.constants.storage",
    "utils.constants.users",
]
# MOCK_MODULES += [
#     "django",
#     "django.apps",
#     "django.conf",
#     "django.conf.settings",
#     "django.contrib",
#     "django.contrib.auth",
#     "django.contrib.auth.models",
#     "django.contrib.auth.mixins",
#     "django.core",
#     "django.core.exceptions",
#     "django.core.signals",
#     "django.db",
#     "django.shortcuts",
#     "django.template",
#     "django.template.defaultfilters",
#     "django.template.loader",
#     "django.urls",
#     "django.utils",
#     "django.utils.module_loading",
#     "django.utils.safestring",
# ]

for mod in MOCK_MODULES:
    sys.modules[mod] = MagicMock()


# -- Project information -----------------------------------------------------

project = "ASA Stats user widgets"
copyright = "2025, ASA Stats DAO"
author = "Ivica Paleka"

release = "0.8.7"

# -- General configuration ---------------------------------------------------

master_doc = "index"

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = ["sphinx.ext.autodoc"]

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

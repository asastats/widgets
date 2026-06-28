"""Loads the shared swap-core manifest once for the shared engine-data views."""

from pathlib import Path

from widgethost.manifest import load_manifest

MANIFEST = load_manifest(Path(__file__).parent / "widget.toml")

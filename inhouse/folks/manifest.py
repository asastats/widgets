"""Loads this widget's manifest once for its view to share."""

from pathlib import Path

from widgethost.manifest import load_manifest

MANIFEST = load_manifest(Path(__file__).parent / "widget.toml")

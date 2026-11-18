# -*- coding: utf-8 -*-
"""Tests for the dark/light theme system: state persistence,
palette completeness, in-place switching and band rendering."""

import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import theme  # noqa: E402
import tzcore  # noqa: E402
from tzcore import AppState, OwnSettings, Partner  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


# ----------------------------------------------------------------------
# State persistence
# ----------------------------------------------------------------------

def test_theme_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    state = AppState(theme="light")
    tzcore.save_state(state)
    loaded = tzcore.load_state()
    assert loaded.theme == "light"


def test_theme_defaults_dark_for_legacy_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = tzcore.settings_path()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"own": {}, "partners": [], "lang": "ja"}, fh)
    assert tzcore.load_state().theme == "dark"


def test_theme_invalid_value_falls_back_to_dark(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = tzcore.settings_path()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"own": {}, "partners": [], "lang": "ja",
                   "theme": "blue"}, fh)
    assert tzcore.load_state().theme == "dark"
    # and saving normalises it back to a valid value
    tzcore.save_state(tzcore.load_state())
    with open(path, encoding="utf-8") as fh:
        assert json.load(fh)["theme"] == "dark"


# ----------------------------------------------------------------------
# Palettes
# ----------------------------------------------------------------------

def test_palettes_have_identical_keys():
    assert set(theme.DARK) == set(theme.LIGHT)
    for pal in (theme.DARK, theme.LIGHT):
        assert len(pal["BAND_STOPS"]) == 11
        assert pal["BAND_STOPS"][0][0] == 0.0
        assert pal["BAND_STOPS"][-1][0] == 24.0


def test_stylesheet_builds_for_both_themes():
    dark = theme.stylesheet(theme.DARK)
    light = theme.stylesheet(theme.LIGHT)
    assert theme.DARK["BG"] in dark
    assert theme.LIGHT["BG"] in light
    assert "check-off.png" in dark
    assert "check-off-lt.png" in light


def test_light_theme_is_a_real_light_palette():
    pal = theme.LIGHT
    # near-white panel, dark text: not a mere inversion of dark
    assert pal["PANEL"] == "#FFFFFF"
    assert pal["INK"] != theme.DARK["INK"]
    assert pal["HEADER"] == "#FFFFFF"


# ----------------------------------------------------------------------
# Switching
# ----------------------------------------------------------------------

def test_apply_theme_switches_app_palette(qapp):
    from PySide6.QtGui import QColor, QPalette
    theme.apply_theme(qapp, "dark")
    assert theme.current_name() == "dark"
    assert (qapp.palette().color(QPalette.ColorRole.Window)
            == QColor(theme.DARK["BG"]))
    theme.apply_theme(qapp, "light")
    assert theme.current_name() == "light"
    assert (qapp.palette().color(QPalette.ColorRole.Window)
            == QColor(theme.LIGHT["BG"]))
    assert theme.BG == theme.LIGHT["BG"]  # dynamic lookup follows
    theme.apply_theme(qapp, "bogus")       # unknown -> dark
    assert theme.current_name() == "dark"


def test_main_window_toggle_saves_and_restores(qapp, tmp_path,
                                               monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    theme.apply_theme(qapp, "dark")
    import app as app_module
    state = AppState(
        own=OwnSettings(zone="Asia/Tokyo", country_code="JP"),
        partners=[Partner(name="NY", country_code="US", city="New York",
                          zone="America/New_York")],
        lang="ja", theme="dark")
    win = app_module.MainWindow(state)
    assert win.theme_name == "dark"
    win._toggle_theme()
    assert win.theme_name == "light"
    assert tzcore.load_state().theme == "light"   # persisted
    win._toggle_theme()
    assert win.theme_name == "dark"
    assert tzcore.load_state().theme == "dark"
    win.close()


def test_theme_toggle_icons_are_drawn(qapp):
    import app as app_module
    for name in ("dark", "light"):
        icon = app_module._theme_icon(name)
        assert not icon.isNull()
        assert not icon.pixmap(26, 26).isNull()


# ----------------------------------------------------------------------
# Band rendering in both themes (incl. long-badge elision)
# ----------------------------------------------------------------------

def test_band_renders_in_both_themes_with_long_badge(qapp):
    from datetime import datetime, timezone
    import bands
    theme.apply_theme(qapp, "dark")
    w = bands.BandWidget()
    w.resize(760, 84)
    w.configure("America/New_York", "09:00", "18:00",
                datetime(2026, 1, 19, 17, 0, tzinfo=timezone.utc),
                dimmed=True,
                badge="Birthday of Martin Luther King, Jr. (observed) — "
                      "a very long holiday name that must not overflow",
                selected=False)
    for name in ("dark", "light"):
        theme.apply_theme(qapp, name)
        w.update()
        img = w.grab().toImage()
        assert img.width() == 760 and img.height() == 84
        # the band is painted (not blank): sample the middle pixel
        assert img.pixelColor(380, 42).alpha() > 0
    w.close()

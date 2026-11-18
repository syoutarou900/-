# -*- coding: utf-8 -*-
"""Theme support: both themes complete, settings round-trip, instant
switching re-skins the panel, settings dialog carries the theme combo.
Run with QT_QPA_PLATFORM=offscreen."""
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod
from themes import THEMES, get_theme


def test_both_themes_complete():
    assert set(THEMES) == {"dark", "light"}
    for name, th in THEMES.items():
        assert th["qss"].strip(), name
        assert set(th["kind_colors"]) == set(appmod.KINDS), name
        for key in ("pinned_card_qss", "pin_on_color", "status_recording",
                    "status_paused", "shadow_top", "shadow_list"):
            assert key in th, (name, key)
        assert len(th["shadow_top"]) == 4 and len(th["shadow_list"]) == 4
    # the two themes really are different skins
    assert THEMES["dark"]["qss"] != THEMES["light"]["qss"]
    assert THEMES["dark"]["kind_colors"] != THEMES["light"]["kind_colors"]


def test_get_theme_fallback():
    assert get_theme("light") is THEMES["light"]
    assert get_theme("nope") is THEMES["dark"]
    assert get_theme(None) is THEMES["dark"]


def test_theme_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "settings_path",
                        lambda: os.path.join(str(tmp_path), "settings.json"))
    s = dict(appmod.DEFAULT_SETTINGS)
    s["theme"] = "light"
    appmod.save_settings(s)
    loaded = appmod.load_settings()
    assert loaded["theme"] == "light"
    # a bogus stored value falls back to dark instead of breaking
    with open(appmod.settings_path(), "w", encoding="utf-8") as f:
        json.dump({"theme": "rainbow"}, f)
    assert appmod.load_settings()["theme"] == "dark"


def _make_panel(tmp_path, monkeypatch, theme=None):
    monkeypatch.setattr(appmod, "config_dir", lambda: str(tmp_path))
    monkeypatch.setattr(appmod, "settings_path",
                        lambda: os.path.join(str(tmp_path), "settings.json"))
    monkeypatch.setattr(appmod, "history_path",
                        lambda: os.path.join(str(tmp_path), "history.json"))
    if theme is not None:
        with open(appmod.settings_path(), "w", encoding="utf-8") as f:
            json.dump({"theme": theme}, f)
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])
    qapp.setQuitOnLastWindowClosed(False)
    panel = appmod.Panel(qapp)
    return qapp, panel


def test_panel_starts_in_saved_theme(tmp_path, monkeypatch):
    qapp, panel = _make_panel(tmp_path, monkeypatch, theme="light")
    assert panel.theme is THEMES["light"]
    panel.quit_app()
    qapp2, panel2 = _make_panel(tmp_path, monkeypatch, theme="dark")
    assert panel2.theme is THEMES["dark"]
    panel2.quit_app()


def test_apply_theme_switches_stylesheet_and_rows(tmp_path, monkeypatch):
    import time
    qapp, panel = _make_panel(tmp_path, monkeypatch)
    panel.store.add("https://a.example", "url", "url", ts=time.time())
    panel.store.add("¥3,000", "amount", "amount_symbol",
                    ts=time.time() + 1)
    panel.refresh_all()
    panel.settings["theme"] = "light"
    panel.apply_theme()
    assert panel.theme is THEMES["light"]
    assert qapp.styleSheet() == THEMES["light"]["qss"]
    # rows were rebuilt under the light theme without losing items
    assert panel.list.count() >= 2
    panel.settings["theme"] = "dark"
    panel.apply_theme()
    assert qapp.styleSheet() == THEMES["dark"]["qss"]
    panel.quit_app()


def test_settings_dialog_theme_combo(tmp_path, monkeypatch):
    qapp, panel = _make_panel(tmp_path, monkeypatch)
    dlg = appmod.SettingsDialog(panel)
    assert dlg.theme_combo.count() == 2
    assert dlg.theme_combo.itemData(0) == "dark"
    assert dlg.theme_combo.itemData(1) == "light"
    dlg.theme_combo.setCurrentIndex(1)
    s = dict(panel.settings)
    dlg.apply_to(s)
    assert s["theme"] == "light"
    dlg.theme_combo.setCurrentIndex(0)
    dlg.apply_to(s)
    assert s["theme"] == "dark"
    panel.quit_app()


def test_light_theme_rtl_and_all_languages(tmp_path, monkeypatch):
    qapp, panel = _make_panel(tmp_path, monkeypatch, theme="light")
    from i18n_data import LANG_ORDER
    for lang in LANG_ORDER:
        panel.settings["language"] = lang
        panel.retranslate()
        panel.refresh_all()
        panel.apply_theme()  # re-skin under every language incl. ar RTL
    panel.quit_app()

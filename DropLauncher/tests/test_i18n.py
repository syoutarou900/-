# -*- coding: utf-8 -*-
import os, re, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import i18n_data
from i18n_data import TRANSLATIONS, LANG_ORDER, LANG_NAMES, t

def _placeholders(s):
    return set(re.findall(r"\{(\w+)\}", s))

def test_i18n_completeness():
    assert LANG_ORDER == ["ja", "en", "es", "zh_CN", "fr", "de", "pt", "ru", "it", "tr", "ar", "id", "ko"]
    assert set(LANG_NAMES) == set(LANG_ORDER)
    base = TRANSLATIONS["ja"]
    assert len(base) >= 90
    for lang in LANG_ORDER:
        d = TRANSLATIONS[lang]
        assert set(d) == set(base), f"{lang}: key set differs"
        for k, v in d.items():
            assert isinstance(v, str) and v.strip(), f"{lang}:{k} empty"
            assert _placeholders(v) == _placeholders(base[k]), f"{lang}:{k} placeholders differ"

def test_i18n_formatting():
    for lang in LANG_ORDER:
        s = t(lang, "run_start", zone="image", count=3)
        assert "image" in s and "3" in s
        s = t(lang, "log_sort", name="a.txt", dest="/tmp/x")
        assert "a.txt" in s

def test_internal_values_unaffected_by_language(tmp_path, monkeypatch):
    import core
    monkeypatch.setattr(core, "APP_DIR", Path(__file__).resolve().parent.parent)
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    app = QApplication.instance() or QApplication([])
    import app as appmod
    w = appmod.MainWindow()
    w.settings["output_base"] = str(tmp_path / "out")
    # switch UI to German via the header selector
    idx = w.lang_combo.findData("de")
    assert idx >= 0
    w.lang_combo.setCurrentIndex(idx)
    assert w.lang == "de"
    # internal enum values stay raw regardless of display language
    assert w.settings["language"] == "de"
    assert w.video_preset.currentData() == "mp4"
    assert w.settings["video_preset"] in ("mp4", "compress", "mp3", "gif")
    dlg = appmod.SettingsDialog(w.settings, w)
    assert dlg.sort_mode.currentData() == w.settings["sort_mode"] == "move"
    assert dlg.sort_sub.currentData() == w.settings["sort_subfolder"] == "ext_date"
    res = dlg.result_settings()
    assert res["sort_mode"] == "move" and res["sort_subfolder"] == "ext_date"
    assert res["image_format"] in ("JPG", "WebP", "PNG")
    dlg.close()
    # zone titles actually re-rendered in German
    titles = {k: z.title for k, z in w.zone_widgets}
    assert titles["sort"] == TRANSLATIONS["de"]["zone_sort_title"]
    # Arabic switches to RTL, Japanese switches back to LTR
    w.lang_combo.setCurrentIndex(w.lang_combo.findData("ar"))
    assert app.layoutDirection() == Qt.RightToLeft
    w.lang_combo.setCurrentIndex(w.lang_combo.findData("ja"))
    assert app.layoutDirection() == Qt.LeftToRight
    assert {k: z.title for k, z in w.zone_widgets}["sort"] == TRANSLATIONS["ja"]["zone_sort_title"]
    w.close()

# -*- coding: utf-8 -*-
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from i18n_data import LANG_NAMES, LANG_ORDER, TRANSLATIONS, t


def test_i18n_completeness():
    # 13言語すべてがそろっていること
    assert LANG_ORDER == ["ja", "en", "es", "zh_CN", "fr", "de", "pt", "ru", "it", "tr", "ar", "id", "ko"]
    assert set(TRANSLATIONS.keys()) == set(LANG_ORDER)
    assert set(LANG_NAMES.keys()) == set(LANG_ORDER)
    base_keys = set(TRANSLATIONS["ja"].keys())
    assert len(base_keys) > 0
    for lang in LANG_ORDER:
        d = TRANSLATIONS[lang]
        # 日本語版と同じキーが全部あること（過不足なし）
        assert set(d.keys()) == base_keys, lang
        for key in base_keys:
            v = d[key]
            assert isinstance(v, str) and v.strip(), (lang, key)
        # ステータス文のプレースホルダが全言語で一致すること
        cleaned = d["status_cleaned"]
        for ph in ("{count}", "{before}", "{after}", "{diff:+d}"):
            assert ph in cleaned, (lang, ph)


def test_status_format_works_in_all_languages():
    for lang in LANG_ORDER:
        s = t(lang, "status_cleaned").format(count=3, before=120, after=100, diff=-20)
        assert "3" in s and "120" in s and "100" in s and "-20" in s, lang
        s2 = t(lang, "status_cleaned").format(count=1, before=10, after=12, diff=2)
        assert "+2" in s2, lang


def test_cleaning_independent_of_ui_language():
    """UI言語を切り替えても、整形結果が一切変わらないこと。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    import app as appmod
    from cleaner import clean_text
    win = appmod.MainWindow()
    samples = [
        "本日は晴天\nなり。明日も　晴れる\nでしょう。",
        "Ｔｅｓｔ１２３とｱｲｳｴｵ、こ ん に ち は　世 界。",
        "The quick brown\nfox    jumps\tover the lazy dog.",
    ]
    # 基準：cleaner を既定設定で直接呼んだ結果
    expected = {}
    for src in samples:
        expected[src] = clean_text(src, win.collect_settings())
    for lang in LANG_ORDER:
        win.apply_language(lang)
        assert win.lang == lang
        # トレイメニューも新しい言語になっていること
        assert win.act_quit.text() == t(lang, "tray_quit")
        assert win.act_show.text() == t(lang, "tray_open_settings")
        for src in samples:
            win.input_edit.setPlainText(src)
            app.processEvents()
            assert win.output_edit.toPlainText() == expected[src], (lang, src)
    # アラビア語では RTL、それ以外では LTR になること
    win.apply_language("ar")
    from PySide6.QtCore import Qt
    assert win.layoutDirection() == Qt.RightToLeft
    win.apply_language("ja")
    assert win.layoutDirection() == Qt.LeftToRight
    # 後続テストへ干渉しないよう、このウィンドウのクリップボード監視を止める
    win.settings["enabled"] = False
    try:
        win.clipboard.dataChanged.disconnect(win.on_clipboard_changed)
    except Exception:
        pass
    win.tray.hide()
    win.hide()
    win.deleteLater()
    app.processEvents()

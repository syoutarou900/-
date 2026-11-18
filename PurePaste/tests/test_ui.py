# -*- coding: utf-8 -*-
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

def test_window_and_clipboard_cleaning():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    import app as appmod
    win = appmod.MainWindow()
    # プレビューが動くこと
    win.input_edit.setPlainText("本日は晴天\nなり。")
    assert win.output_edit.toPlainText() == "本日は晴天なり。"
    # クリップボードに汚いテキストを入れると整形されて戻ること
    app.clipboard().setText("Ｔｅｓｔ１２３\nです")
    app.processEvents()
    assert app.clipboard().text() == "Test123です"
    # OFFにすると整形しないこと
    win.settings["enabled"] = False
    app.clipboard().setText("Ｔｅｓｔ")
    app.processEvents()
    assert app.clipboard().text() == "Ｔｅｓｔ"
    win.settings["enabled"] = True
    # 元に戻す
    win.restore_original()
    app.processEvents()
    assert app.clipboard().text() == "Ｔｅｓｔ１２３\nです"

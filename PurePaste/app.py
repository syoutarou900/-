# -*- coding: utf-8 -*-
"""
PurePaste
コピーした瞬間にクリップボードのテキストを自動で綺麗に整形する常駐アプリ。
- タスクトレイに常駐し、クリップボードの変化を監視
- 変な改行 / 不必要なスペース / 全角半角の混在 を自動整形
- ウィンドウを閉じてもトレイに残る（終了はトレイメニューから）
- 画面表示は13言語に切替可能（i18n_data.py）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMenu, QMessageBox, QPushButton, QSystemTrayIcon, QTextEdit,
    QVBoxLayout, QWidget,
)

from cleaner import DEFAULT_SETTINGS, clean_text
from i18n_data import LANG_NAMES, LANG_ORDER, t

APP_NAME = "PurePaste"

# 整形ルールの設定キー（表示名・説明は i18n_data.py の各言語辞書から引く）
OPTION_KEYS = [
    "join_lines",
    "collapse_spaces",
    "trim_lines",
    "fullwidth_alnum_half",
    "halfwidth_kana_full",
    "fullwidth_space_half",
    "remove_jp_spaces",
    "collapse_blank_lines",
    "notify",
]

SAMPLE_TEXT = (
    "本日は晴天\n"
    "なり。明日も　晴れる\n"
    "でしょう。\n"
    "\n"
    "\n"
    "Ｔｅｓｔ１２３とｱｲｳｴｵ、こ ん に ち は　世 界。\n"
    "The quick brown\n"
    "fox    jumps\tover the lazy dog."
)


def config_dir():
    if sys.platform == "darwin":
        # macOS標準の保存先: ~/Library/Application Support/PurePaste
        path = os.path.join(os.path.expanduser("~"),
                            "Library", "Application Support", "PurePaste")
    else:
        base = os.environ.get("APPDATA")
        if base:
            path = os.path.join(base, "PurePaste")
        else:
            path = os.path.join(os.path.expanduser("~"), ".purepaste")
    os.makedirs(path, exist_ok=True)
    return path


def settings_path():
    return os.path.join(config_dir(), "settings.json")


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    data = {}
    try:
        with open(settings_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    s.update({k: v for k, v in data.items() if k in s})
    lang = data.get("language", "ja")
    s["language"] = lang if lang in LANG_ORDER else "ja"
    return s


def save_settings(s):
    try:
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def set_autostart(enable):
    """Windows起動時の自動開始（レジストリ HKCU Run）。Windows以外では何もしない。
    macOSではこの設定は効きません（手動登録の方法は README の Mac 章を参照）。"""
    if sys.platform != "win32":
        return
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        if enable:
            if getattr(sys, "frozen", False):
                cmd = '"%s"' % sys.executable
            else:
                cmd = '"%s" "%s"' % (sys.executable, os.path.abspath(__file__))
            winreg.SetValueEx(key, "PurePaste", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, "PurePaste")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass


def make_icon(paused=False):
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    color = QColor("#9aa5b1") if paused else QColor("#2f7fe0")
    p.setBrush(color)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 14, 14)
    p.setPen(QColor("white"))
    f = QFont()
    f.setPixelSize(30)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignCenter, "P")
    p.end()
    return QIcon(pix)


STYLE = """
QMainWindow { background: #eef3f9; }
QFrame#card { background: white; border: 1px solid #d5dee9; border-radius: 12px; }
QLabel#title { font-size: 20px; font-weight: bold; color: #173a5e; }
QLabel#sub { font-size: 12px; color: #5a6b7f; }
QLabel#sect { font-size: 14px; font-weight: bold; color: #173a5e; }
QLabel#lang { font-size: 12px; font-weight: bold; color: #173a5e; }
QComboBox { background: white; color: #173a5e; border: 1px solid #2568bd; border-bottom: 3px solid #1d549c;
  border-radius: 9px; padding: 6px 10px; font-size: 13px; font-weight: bold; min-width: 130px; }
QComboBox:hover { border-color: #3b8ae8; }
QComboBox::drop-down { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #4a97f0, stop:1 #2f7fe0);
  border: none; border-top-right-radius: 8px; border-bottom-right-radius: 8px; width: 24px; }
QComboBox QAbstractItemView { background: white; color: #22303f; selection-background-color: #2f7fe0; selection-color: white; }
QCheckBox { font-size: 13px; color: #22303f; spacing: 8px; }
QLabel#desc { font-size: 11px; color: #75859a; }
QTextEdit { background: #fbfdfe; border: 1px solid #c9d6e4; border-radius: 8px; font-size: 13px; padding: 6px; }
QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #4a97f0, stop:1 #2f7fe0);
  color: white; border: 1px solid #2568bd; border-bottom: 3px solid #1d549c; border-radius: 9px;
  padding: 8px 16px; font-size: 13px; font-weight: bold; }
QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #63a8f5, stop:1 #3b8ae8); }
QPushButton:pressed { background: #2568bd; }
QPushButton#ghost { background: white; color: #2f5b8f; border: 1px solid #b9c9dc; border-bottom: 3px solid #9fb4cc; }
QPushButton#onoff[on="true"] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #3ec97e, stop:1 #22a862);
  border: 1px solid #1c8a4f; border-bottom: 3px solid #146c3d; font-size: 15px; padding: 12px; }
QPushButton#onoff[on="false"] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #b6c0cc, stop:1 #8d9aa9);
  border: 1px solid #76848f; border-bottom: 3px solid #5d6b78; font-size: 15px; padding: 12px; }
QLabel#status { font-size: 12px; color: #2c6e49; font-weight: bold; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(760, 720)
        self.setStyleSheet(STYLE)
        self.settings = load_settings()
        self.lang = self.settings.get("language", "ja")
        self.checks = {}
        self.descs = {}
        self.cleaned_count = 0
        self.last_original = ""
        self._writing_clipboard = False
        self._last_seen = ""
        self._status = ("started",)

        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        head.addWidget(title)
        head.addStretch(1)
        self.lang_label = QLabel(self._t("language_label"))
        self.lang_label.setObjectName("lang")
        head.addWidget(self.lang_label)
        self.lang_combo = QComboBox()
        for code in LANG_ORDER:
            self.lang_combo.addItem(LANG_NAMES[code], code)
        self.lang_combo.setCurrentIndex(LANG_ORDER.index(self.lang))
        self.lang_combo.currentIndexChanged.connect(self.on_language_changed)
        head.addWidget(self.lang_combo)
        lay.addLayout(head)

        self.sub_label = QLabel(self._t("subtitle"))
        self.sub_label.setObjectName("sub")
        self.sub_label.setWordWrap(True)
        lay.addWidget(self.sub_label)

        self.onoff_btn = QPushButton()
        self.onoff_btn.setObjectName("onoff")
        self.onoff_btn.clicked.connect(self.toggle_enabled)
        lay.addWidget(self.onoff_btn)

        card = QFrame(); card.setObjectName("card")
        card_lay = QVBoxLayout(card); card_lay.setContentsMargins(14, 12, 14, 12); card_lay.setSpacing(4)
        self.sect_label = QLabel(self._t("options_title")); self.sect_label.setObjectName("sect")
        card_lay.addWidget(self.sect_label)
        for key in OPTION_KEYS:
            cb = QCheckBox(self._t(key))
            cb.setChecked(bool(self.settings.get(key, False)))
            cb.stateChanged.connect(self.on_option_changed)
            self.checks[key] = cb
            card_lay.addWidget(cb)
            d = QLabel(self._t(key + "_desc")); d.setObjectName("desc"); d.setWordWrap(True)
            d.setContentsMargins(26, 0, 0, 4)
            self.descs[key] = d
            card_lay.addWidget(d)
        self.autostart_cb = QCheckBox(self._t("autostart_label"))
        self.autostart_cb.setChecked(bool(self.settings.get("autostart", False)))
        self.autostart_cb.stateChanged.connect(self.on_option_changed)
        card_lay.addWidget(self.autostart_cb)
        lay.addWidget(card)

        card2 = QFrame(); card2.setObjectName("card")
        c2 = QVBoxLayout(card2); c2.setContentsMargins(14, 12, 14, 12); c2.setSpacing(8)
        self.sect2_label = QLabel(self._t("test_title")); self.sect2_label.setObjectName("sect")
        c2.addWidget(self.sect2_label)
        row = QHBoxLayout()
        self.input_edit = QTextEdit(); self.input_edit.setPlaceholderText(self._t("input_placeholder"))
        self.output_edit = QTextEdit(); self.output_edit.setReadOnly(True); self.output_edit.setPlaceholderText(self._t("output_placeholder"))
        self.input_edit.textChanged.connect(self.update_preview)
        row.addWidget(self.input_edit); row.addWidget(self.output_edit)
        c2.addLayout(row)
        brow = QHBoxLayout()
        self.sample_btn = QPushButton(self._t("sample_btn")); self.sample_btn.setObjectName("ghost")
        self.sample_btn.clicked.connect(lambda: self.input_edit.setPlainText(SAMPLE_TEXT))
        self.copy_btn = QPushButton(self._t("copy_btn"))
        self.copy_btn.clicked.connect(self.copy_output)
        brow.addWidget(self.sample_btn); brow.addWidget(self.copy_btn); brow.addStretch(1)
        c2.addLayout(brow)
        lay.addWidget(card2)

        self.status_label = QLabel()
        self.status_label.setObjectName("status")
        lay.addWidget(self.status_label)
        self.note_label = QLabel(self._t("note_resident"))
        self.note_label.setObjectName("desc"); self.note_label.setWordWrap(True)
        lay.addWidget(self.note_label)

        self.setLayoutDirection(Qt.RightToLeft if self.lang == "ar" else Qt.LeftToRight)
        self._setup_tray()
        self._setup_clipboard()
        self._refresh_onoff()
        self._render_status()
        self.update_preview()

    # ---------- 言語 ----------
    def _t(self, key):
        return t(self.lang, key)

    def on_language_changed(self, index):
        code = LANG_ORDER[index]
        if code == self.lang:
            return
        self.apply_language(code)
        self.settings = self.collect_settings()
        save_settings(self.settings)

    def apply_language(self, lang):
        """表示言語を即時切替する（設定画面の再描画＋トレイメニューの再構築）。"""
        if lang not in LANG_ORDER:
            lang = "ja"
        self.lang = lang
        self.setLayoutDirection(Qt.RightToLeft if lang == "ar" else Qt.LeftToRight)
        idx = LANG_ORDER.index(lang)
        if self.lang_combo.currentIndex() != idx:
            self.lang_combo.blockSignals(True)
            self.lang_combo.setCurrentIndex(idx)
            self.lang_combo.blockSignals(False)
        self.lang_label.setText(self._t("language_label"))
        self.sub_label.setText(self._t("subtitle"))
        self.sect_label.setText(self._t("options_title"))
        for key, cb in self.checks.items():
            cb.setText(self._t(key))
        for key, d in self.descs.items():
            d.setText(self._t(key + "_desc"))
        self.autostart_cb.setText(self._t("autostart_label"))
        self.sect2_label.setText(self._t("test_title"))
        self.input_edit.setPlaceholderText(self._t("input_placeholder"))
        self.output_edit.setPlaceholderText(self._t("output_placeholder"))
        self.sample_btn.setText(self._t("sample_btn"))
        self.copy_btn.setText(self._t("copy_btn"))
        self.note_label.setText(self._t("note_resident"))
        # トレイメニューの項目も新しい言語で表示し直す
        self.act_show.setText(self._t("tray_open_settings"))
        self.act_pause.setText(self._t("tray_pause_resume"))
        self.act_restore.setText(self._t("tray_restore"))
        self.act_quit.setText(self._t("tray_quit"))
        self._refresh_onoff()
        self._render_status()

    def _render_status(self):
        kind = self._status[0]
        if kind == "cleaned":
            _, count, before, after, diff = self._status
            self.status_label.setText(self._t("status_cleaned").format(
                count=count, before=before, after=after, diff=diff))
        elif kind == "restored":
            self.status_label.setText(self._t("status_restored"))
        else:
            self.status_label.setText(self._t("status_started"))

    # ---------- 設定 ----------
    def collect_settings(self):
        s = dict(self.settings)
        s["enabled"] = bool(s.get("enabled", True))
        for key, cb in self.checks.items():
            s[key] = cb.isChecked()
        s["autostart"] = self.autostart_cb.isChecked()
        s["language"] = self.lang
        return s

    def on_option_changed(self, *_):
        self.settings = self.collect_settings()
        save_settings(self.settings)
        set_autostart(self.settings.get("autostart", False))
        self.update_preview()

    def toggle_enabled(self):
        self.settings["enabled"] = not bool(self.settings.get("enabled", True))
        save_settings(self.settings)
        self._refresh_onoff()
        self._refresh_tray()

    def _refresh_onoff(self):
        on = bool(self.settings.get("enabled", True))
        self.onoff_btn.setText(self._t("onoff_on") if on else self._t("onoff_off"))
        self.onoff_btn.setProperty("on", "true" if on else "false")
        self.onoff_btn.style().unpolish(self.onoff_btn); self.onoff_btn.style().polish(self.onoff_btn)

    # ---------- トレイ ----------
    def _setup_tray(self):
        self.tray = QSystemTrayIcon(make_icon(not self.settings.get("enabled", True)), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        self.act_show = QAction(self._t("tray_open_settings"), self); self.act_show.triggered.connect(self.show_and_raise)
        self.act_pause = QAction(self._t("tray_pause_resume"), self); self.act_pause.triggered.connect(self.toggle_enabled)
        self.act_restore = QAction(self._t("tray_restore"), self); self.act_restore.triggered.connect(self.restore_original)
        self.act_quit = QAction(self._t("tray_quit"), self); self.act_quit.triggered.connect(self.quit_app)
        menu.addAction(self.act_show); menu.addAction(self.act_pause); menu.addAction(self.act_restore)
        menu.addSeparator(); menu.addAction(self.act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _refresh_tray(self):
        self.tray.setIcon(make_icon(not self.settings.get("enabled", True)))

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_and_raise()

    def show_and_raise(self):
        self.show(); self.raise_(); self.activateWindow()

    def quit_app(self):
        save_settings(self.collect_settings())
        QApplication.quit()

    def closeEvent(self, event):
        # 閉じる = トレイに隠れる（常駐を続ける）
        event.ignore()
        self.hide()
        self.tray.showMessage(APP_NAME, self._t("tray_resident_msg"),
                              QSystemTrayIcon.Information, 2500)

    # ---------- クリップボード監視 ----------
    def _setup_clipboard(self):
        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self.on_clipboard_changed)

    def on_clipboard_changed(self):
        if self._writing_clipboard:
            return
        if not self.settings.get("enabled", True):
            return
        try:
            text = self.clipboard.text()
        except Exception:
            return
        if not text or text == self._last_seen:
            return
        self._last_seen = text
        if len(text) > 1000000:
            return
        cleaned = clean_text(text, self.collect_settings())
        if cleaned == text:
            return
        self.last_original = text
        self._writing_clipboard = True
        try:
            self.clipboard.setText(cleaned)
        finally:
            QTimer.singleShot(0, self._clear_writing_flag)
        self._last_seen = cleaned
        self.cleaned_count += 1
        diff = len(text) - len(cleaned)
        self._status = ("cleaned", self.cleaned_count, len(text), len(cleaned), diff)
        self._render_status()
        if self.settings.get("notify", False):
            self.tray.showMessage(APP_NAME, self._t("notify_cleaned"), QSystemTrayIcon.Information, 1500)

    def _clear_writing_flag(self):
        self._writing_clipboard = False

    def restore_original(self):
        if not self.last_original:
            self.tray.showMessage(APP_NAME, self._t("notify_none"), QSystemTrayIcon.Information, 2000)
            return
        self._writing_clipboard = True
        try:
            self.clipboard.setText(self.last_original)
        finally:
            QTimer.singleShot(0, self._clear_writing_flag)
        self._last_seen = self.last_original
        self._status = ("restored",)
        self._render_status()

    # ---------- プレビュー ----------
    def update_preview(self):
        src = self.input_edit.toPlainText()
        self.output_edit.setPlainText(clean_text(src, self.collect_settings()) if src else "")

    def copy_output(self):
        txt = self.output_edit.toPlainText()
        if txt:
            self._last_seen = txt  # 自分で入れたものは再整形しない目印
            QApplication.clipboard().setText(txt)


def main():
    app = QApplication(sys.argv)
    try:
        import os as _os, sys as _sys
        from PySide6.QtGui import QIcon as _QIcon
        _ib = getattr(_sys, "_MEIPASS", None) or _os.path.dirname(_os.path.abspath(__file__))
        _ip = _os.path.join(_ib, "assets", "icon.png")
        if _os.path.exists(_ip):
            app.setWindowIcon(_QIcon(_ip))
    except Exception:
        pass
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    win = MainWindow()
    # 起動時はウィンドウ表示（初回に設定を確認してもらう）。トレイ常駐が本体。
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

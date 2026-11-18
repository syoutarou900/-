# -*- coding: utf-8 -*-
"""
ClipStock - コピペ履歴・スマートウォッチャー
Clipboard-history resident app.

- Watches the clipboard and stores copied text, auto-classified into
  kinds (URL / amount / date / address / code / email / other) by
  deterministic patterns only, each with a human-readable reason.
- Items are grouped into "work sets" (auto-split after a quiet gap,
  or manually). Open the panel (tray / Ctrl+Shift+V on Windows), pick
  an item, and it goes back onto the clipboard; pasting itself is
  always done by the user (Ctrl+V). The app never pastes by itself.
- History is stored ONLY locally (JSON under the per-user app data
  folder). No network communication of any kind.
- Privacy: auto-expiry (default 24h), recording pause, and card-number
  shaped text (Luhn) is not stored by default.
- UI in 13 languages with instant switching (i18n_data.py).
"""
import ctypes
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import (QAction, QColor, QCursor, QFont, QFontDatabase,
                           QIcon, QKeySequence, QShortcut)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QGraphicsDropShadowEffect, QHBoxLayout, QInputDialog,
    QFrame, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSystemTrayIcon,
    QVBoxLayout, QWidget,
)

from appinfo import APP_ID, APP_NAME_EN, APP_NAME_JA, HOTKEY_LABEL, VERSION
from classifier import classify, is_sensitive
from i18n_data import LANG_NAMES, LANG_ORDER, RTL_LANGS, t
from store import Store

MAX_STORED_TEXT = 100000     # robustness: never store gigantic copies
MAX_ITEMS = 2000             # housekeeping cap (oldest unpinned dropped)

DEFAULT_SETTINGS = {
    "language": "ja",
    "expire": "24h",         # 1h / 24h / 7d / 30d / never
    "gap_minutes": 30,       # work-set auto-split gap
    "block_sensitive": True,
    "autostart": False,
    "paused": False,
    "theme": "dark",         # dark / light
}
EXPIRE_SECONDS = {"1h": 3600, "24h": 86400, "7d": 604800,
                  "30d": 2592000, "never": None}
EXPIRE_KEYS = [("1h", "expire_1h"), ("24h", "expire_24h"), ("7d", "expire_7d"),
               ("30d", "expire_30d"), ("never", "expire_never")]
GAP_OPTIONS = [(10, "gap_10m"), (30, "gap_30m"), (60, "gap_60m")]
KINDS = ["url", "email", "amount", "date", "address", "code", "other"]

from themes import FONT_FAMILIES, THEMES, get_theme  # noqa: E402

BUNDLED_FONTS = ("Inter-Regular.ttf", "Inter-Medium.ttf",
                 "Inter-SemiBold.ttf", "Inter-Bold.ttf")


def load_app_fonts():
    """Register the bundled Inter typeface (assets/fonts) with Qt.

    Inter covers Latin text and digits with a modern, even look on
    every platform; glyphs it lacks (e.g. Japanese) fall back through
    FONT_FAMILIES to the platform's native UI fonts.
    """
    for name in BUNDLED_FONTS:
        try:
            QFontDatabase.addApplicationFont(asset_path("fonts/" + name))
        except Exception:
            pass

# Backward-compatible aliases (the dark theme is the original design).
KIND_COLORS = THEMES["dark"]["kind_colors"]
QSS = THEMES["dark"]["qss"]


def config_dir():
    if sys.platform == "darwin":
        path = os.path.join(os.path.expanduser("~"),
                            "Library", "Application Support", APP_ID)
    else:
        base = os.environ.get("APPDATA")
        if base:
            path = os.path.join(base, APP_ID)
        else:
            path = os.path.join(os.path.expanduser("~"), "." + APP_ID.lower())
    os.makedirs(path, exist_ok=True)
    return path


def settings_path():
    return os.path.join(config_dir(), "settings.json")


def history_path():
    return os.path.join(config_dir(), "history.json")


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(settings_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        s.update({k: v for k, v in data.items() if k in s})
    except Exception:
        pass
    if s["language"] not in LANG_ORDER:
        s["language"] = "ja"
    if s["expire"] not in EXPIRE_SECONDS:
        s["expire"] = "24h"
    if s["gap_minutes"] not in (10, 30, 60):
        s["gap_minutes"] = 30
    if s["theme"] not in THEMES:
        s["theme"] = "dark"
    return s


def save_settings(s):
    try:
        with open(settings_path(), "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def set_autostart(enable):
    """Windows autostart via HKCU Run. No-op elsewhere (the Mac manual
    explains the manual Login Items route)."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE)
        if enable:
            if getattr(sys, "frozen", False):
                cmd = '"%s" --tray' % sys.executable
            else:
                cmd = '"%s" "%s" --tray' % (sys.executable,
                                            os.path.abspath(__file__))
            winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, APP_ID)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass


def asset_path(name):
    base = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(base, "assets", name)
    if os.path.exists(p):
        return p
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        p2 = os.path.join(meipass, "assets", name)
        if os.path.exists(p2):
            return p2
    return p


# ----------------------------------------------------------------------
# Windows global hotkey (Ctrl+Shift+V) via RegisterHotKey.
# ----------------------------------------------------------------------
class _MSG(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint),
                ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_ssize_t),
                ("time", ctypes.c_uint), ("pt_x", ctypes.c_long),
                ("pt_y", ctypes.c_long)]


class HotkeyThread(QThread):
    """Global hotkey (Ctrl+Shift+V) on a dedicated worker thread (Windows).

    The hotkey is registered on this thread and its Win32 message loop runs
    here, so the GUI thread's Qt event dispatcher never touches raw native
    messages. (An earlier design used QAbstractNativeEventFilter +
    RegisterHotKey on the GUI thread; under Wine that destabilised the Qt
    event loop within seconds — page fault inside Qt6Core — so it was
    replaced with this thread-based design.)
    """

    triggered = Signal()
    HOTKEY_ID = 0xC57C
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012

    def __init__(self, parent=None):
        super().__init__(parent)
        self.registered = False
        self._tid = None

    def run(self):
        if sys.platform != "win32":
            return
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            self._tid = kernel32.GetCurrentThreadId()
            MOD_CONTROL, MOD_SHIFT, VK_V = 0x0002, 0x0004, 0x56
            if not user32.RegisterHotKey(None, self.HOTKEY_ID,
                                         MOD_CONTROL | MOD_SHIFT, VK_V):
                return
            self.registered = True
            msg = _MSG()
            while True:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret <= 0:
                    break
                if msg.message == self.WM_HOTKEY and msg.wParam == self.HOTKEY_ID:
                    self.triggered.emit()
            user32.UnregisterHotKey(None, self.HOTKEY_ID)
            self.registered = False
        except Exception:
            self.registered = False

    def stop(self):
        if self._tid:
            try:
                ctypes.windll.user32.PostThreadMessageW(
                    self._tid, self.WM_QUIT, 0, 0)
            except Exception:
                pass
        self.wait(2000)



class ItemRow(QWidget):
    """One history row: accent bar, kind badge, excerpt, meta, actions.

    Pinned items are unmistakable: gold accent bar, warm-tinted card and
    a filled "pinned" badge next to the gold star.
    """

    def __init__(self, panel, item):
        super().__init__()
        self.setObjectName("rowCard")
        self.panel = panel
        self.item = item
        theme = panel.theme
        if item["pinned"]:
            self.setStyleSheet(theme["pinned_card_qss"])
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 9, 8)
        lay.setSpacing(9)

        def _grad(hex_color):
            c = QColor(hex_color)
            return ("background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                    "stop:0 %s, stop:1 %s);" % (c.lighter(118).name(),
                                               c.darker(106).name()))

        bar = QLabel()
        bar.setFixedWidth(4)
        bar_color = theme["pin_bar"] if item["pinned"] else theme[
            "kind_colors"].get(item["kind"], "#94A3B8")
        bar.setStyleSheet(_grad(bar_color) + " border-radius:2px;")
        lay.addWidget(bar)

        chip = QLabel(panel.tt("kind_" + item["kind"]))
        chip.setObjectName("kindChip")
        chip.setStyleSheet(_grad(theme["kind_colors"].get(
            item["kind"], "#94A3B8")))
        chip.setAlignment(Qt.AlignCenter)
        chip.setMinimumWidth(58)
        lay.addWidget(chip, 0, Qt.AlignTop)

        mid = QVBoxLayout()
        mid.setSpacing(1)
        preview = " ".join(item["text"].split())
        if len(preview) > 95:
            preview = preview[:95] + "…"
        text_label = QLabel(preview)
        text_label.setObjectName("rowText")
        text_label.setToolTip(item["text"][:2000])
        mid.addWidget(text_label)
        lt = time.localtime(item["ts"])
        meta = QLabel("%s  ·  %s" % (
            time.strftime("%m/%d %H:%M", lt),
            panel.tt("reason_" + item["reason"])))
        meta.setObjectName("rowMeta")
        mid.addWidget(meta)
        lay.addLayout(mid, 1)

        if item["pinned"]:
            badge = QLabel(panel.tt("pinned_badge"))
            badge.setObjectName("pinnedBadge")
            lay.addWidget(badge, 0, Qt.AlignTop)

        pin_btn = QPushButton("★" if item["pinned"] else "☆")
        pin_btn.setObjectName("miniBtn")
        pin_btn.setProperty("class", "miniBtn")
        pin_btn.setToolTip(panel.tt("unpin" if item["pinned"] else "pin"))
        if item["pinned"]:
            pin_btn.setStyleSheet(
                "color:%s;" % theme["pin_on_color"])
        pin_btn.clicked.connect(
            lambda _=False, iid=item["id"]: panel.toggle_pin(iid))
        lay.addWidget(pin_btn, 0, Qt.AlignTop)

        del_btn = QPushButton("×")
        del_btn.setProperty("class", "miniBtn")
        del_btn.setToolTip(panel.tt("delete_item"))
        del_btn.clicked.connect(
            lambda _=False, iid=item["id"]: panel.delete_item(iid))
        lay.addWidget(del_btn, 0, Qt.AlignTop)


class SetHeader(QWidget):
    """Divider row in the list: work-set name, its time span, item count."""

    def __init__(self, panel, name, span_text, count):
        super().__init__()
        self.setObjectName("setHeader")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(11, 5, 11, 5)
        lay.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet("background:#7C6FF0; border-radius:4px;")
        lay.addWidget(dot)
        title = QLabel(name)
        title.setObjectName("setHeaderTitle")
        lay.addWidget(title)
        lay.addStretch(1)
        meta = QLabel("%s · %s" % (span_text,
                                   panel.tt("count_fmt", count=count)))
        meta.setObjectName("setHeaderMeta")
        lay.addWidget(meta)


class SettingsDialog(QDialog):
    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.setWindowTitle(panel.tt("settings_title"))
        self.setMinimumWidth(430)
        lay = QVBoxLayout(self)
        lay.setSpacing(11)
        lay.setContentsMargins(18, 16, 18, 16)
        s = panel.settings

        def row(label_key, widget):
            r = QHBoxLayout()
            lab = QLabel(panel.tt(label_key))
            lab.setMinimumWidth(170)
            r.addWidget(lab)
            r.addWidget(widget, 1)
            lay.addLayout(r)

        self.lang_combo = QComboBox()
        for code in LANG_ORDER:
            self.lang_combo.addItem(LANG_NAMES[code], code)
        self.lang_combo.setCurrentIndex(LANG_ORDER.index(s["language"]))
        row("language_label", self.lang_combo)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem(panel.tt("theme_dark"), "dark")
        self.theme_combo.addItem(panel.tt("theme_light"), "light")
        self.theme_combo.setCurrentIndex(
            1 if s.get("theme", "dark") == "light" else 0)
        row("theme_label", self.theme_combo)

        self.expire_combo = QComboBox()
        for value, key in EXPIRE_KEYS:
            self.expire_combo.addItem(panel.tt(key), value)
        idx = [v for v, _ in EXPIRE_KEYS].index(s["expire"])
        self.expire_combo.setCurrentIndex(idx)
        row("expire_label", self.expire_combo)

        self.gap_combo = QComboBox()
        for value, key in GAP_OPTIONS:
            self.gap_combo.addItem(panel.tt(key), value)
        idx = [v for v, _ in GAP_OPTIONS].index(s["gap_minutes"])
        self.gap_combo.setCurrentIndex(idx)
        row("gap_label", self.gap_combo)

        self.block_cb = QCheckBox(panel.tt("block_sensitive_label"))
        self.block_cb.setChecked(bool(s["block_sensitive"]))
        lay.addWidget(self.block_cb)

        self.pause_cb = QCheckBox(panel.tt("pause_label"))
        self.pause_cb.setChecked(bool(s["paused"]))
        lay.addWidget(self.pause_cb)

        self.autostart_cb = None
        if sys.platform == "win32":
            self.autostart_cb = QCheckBox(panel.tt("autostart_label"))
            self.autostart_cb.setChecked(bool(s["autostart"]))
            lay.addWidget(self.autostart_cb)

        note = QLabel(panel.tt("privacy_note"))
        note.setObjectName("noteBox")
        note.setWordWrap(True)
        lay.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(panel.tt("ok"))
        buttons.button(QDialogButtonBox.Cancel).setText(panel.tt("cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def apply_to(self, settings):
        settings["language"] = self.lang_combo.currentData()
        settings["theme"] = self.theme_combo.currentData()
        settings["expire"] = self.expire_combo.currentData()
        settings["gap_minutes"] = self.gap_combo.currentData()
        settings["block_sensitive"] = self.block_cb.isChecked()
        settings["paused"] = self.pause_cb.isChecked()
        if self.autostart_cb is not None:
            settings["autostart"] = self.autostart_cb.isChecked()
        return settings


class Panel(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app_ref = app
        self.first_run = not os.path.exists(settings_path())
        self.settings = load_settings()
        self.store = Store.load(history_path(),
                                gap_seconds=self.settings["gap_minutes"] * 60)
        self.lang = self.settings["language"]
        self.theme = get_theme(self.settings["theme"])
        self._setting_clipboard = False
        self._last_block_notice = 0.0
        self._filter_kind = None       # None = all kinds
        self._selected_set = None      # None = all sets
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_now)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self.refresh_list)

        self.setWindowTitle("%s - %s" % (APP_NAME_EN, APP_NAME_JA))
        self.setWindowIcon(QIcon(asset_path("icon.png")))
        self.resize(600, 660)
        self.setMinimumSize(480, 520)
        self._build_ui()
        self.tray = None
        self.retranslate()
        self._run_expire()
        self.refresh_all()

        clipboard = QApplication.clipboard()
        clipboard.dataChanged.connect(self.on_clipboard_changed)
        expire_timer = QTimer(self)
        expire_timer.timeout.connect(self._run_expire)
        expire_timer.start(10 * 60 * 1000)
        self._expire_timer = expire_timer

        self.hotkey = HotkeyThread(self)
        self.hotkey.triggered.connect(self.toggle_panel)
        if sys.platform == "win32":
            # Start the tray icon and the global hotkey a few seconds
            # after launch: creating them inside the first moments of
            # process startup proved fragile under Wine (intermittent
            # Qt6Core page fault at startup), and a short delay is
            # invisible in normal use.
            QTimer.singleShot(2500, self._build_tray)
            QTimer.singleShot(4000, self.hotkey.start)

    # ---------- helpers ----------
    def tt(self, key, **kw):
        return t(self.lang, key, **kw)

    def _save_soon(self):
        self._save_timer.start(400)

    def _save_now(self):
        try:
            self.store.save(history_path())
        except Exception:
            pass
        save_settings(self.settings)

    def _run_expire(self):
        ttl = EXPIRE_SECONDS.get(self.settings["expire"])
        try:
            removed = self.store.expire(ttl)
        except Exception:
            removed = 0
        if removed:
            self._save_soon()
            self.refresh_all()

    def _housekeep(self):
        # Cap total items so the JSON and the panel stay light forever.
        if len(self.store.items) > MAX_ITEMS:
            excess = len(self.store.items) - MAX_ITEMS
            kept = []
            for i in self.store.items:
                if excess > 0 and not i["pinned"]:
                    excess -= 1
                    continue
                kept.append(i)
            self.store.items = kept

    # ---------- UI ----------
    def _build_ui(self):
        central = QWidget()
        central.setObjectName("centralRoot")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # Sticky control card: title, search and filters stay pinned at
        # the top while only the history list scrolls underneath.
        top = QFrame()
        top.setObjectName("topCard")
        shadow = QGraphicsDropShadowEffect(top)
        shadow.setBlurRadius(self.theme["shadow_top_blur"])
        shadow.setOffset(0, self.theme["shadow_top_dy"])
        shadow.setColor(QColor(*self.theme["shadow_top"]))
        top.setGraphicsEffect(shadow)
        self._top_shadow = shadow
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(13, 11, 13, 11)
        top_lay.setSpacing(8)

        head = QHBoxLayout()
        icon_lab = QLabel()
        pix = QIcon(asset_path("icon.png")).pixmap(40, 40)
        icon_lab.setPixmap(pix)
        head.addWidget(icon_lab)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title_label = QLabel(APP_NAME_EN)
        self.title_label.setObjectName("appTitle")
        titles.addWidget(self.title_label)
        self.sub_label = QLabel()
        self.sub_label.setObjectName("appSub")
        self.sub_label.setWordWrap(True)
        titles.addWidget(self.sub_label)
        head.addLayout(titles, 1)
        self.status_label = QLabel()
        self.status_label.setObjectName("statusDot")
        head.addWidget(self.status_label)
        top_lay.addLayout(head)

        self.search_edit = QLineEdit()
        self.search_edit.textChanged.connect(
            lambda _s: self._search_timer.start(120))
        top_lay.addWidget(self.search_edit)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.chip_group = QButtonGroup(self)
        self.chip_group.setExclusive(True)
        self.chip_buttons = {}
        all_btn = QPushButton()
        all_btn.setProperty("class", "chip")
        all_btn.setCheckable(True)
        all_btn.setChecked(True)
        all_btn.clicked.connect(lambda: self._set_filter(None))
        self.chip_group.addButton(all_btn)
        chips.addWidget(all_btn)
        self.chip_buttons[None] = all_btn
        for kind in KINDS:
            b = QPushButton()
            b.setProperty("class", "chip")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=kind: self._set_filter(k))
            self.chip_group.addButton(b)
            chips.addWidget(b)
            self.chip_buttons[kind] = b
        chips.addStretch(1)
        top_lay.addLayout(chips)

        set_row = QHBoxLayout()
        self.set_label = QLabel()
        set_row.addWidget(self.set_label)
        self.set_combo = QComboBox()
        self.set_combo.currentIndexChanged.connect(self._on_set_changed)
        set_row.addWidget(self.set_combo, 1)
        self.new_set_btn = QPushButton()
        self.new_set_btn.setObjectName("accentBtn")
        self.new_set_btn.clicked.connect(self.start_new_set)
        set_row.addWidget(self.new_set_btn)
        self.rename_btn = QPushButton()
        self.rename_btn.clicked.connect(self.rename_current_set)
        set_row.addWidget(self.rename_btn)
        top_lay.addLayout(set_row)
        root.addWidget(top)

        self.list = QListWidget()
        list_shadow = QGraphicsDropShadowEffect(self.list)
        list_shadow.setBlurRadius(self.theme["shadow_list_blur"])
        list_shadow.setOffset(0, self.theme["shadow_list_dy"])
        list_shadow.setColor(QColor(*self.theme["shadow_list"]))
        self.list.setGraphicsEffect(list_shadow)
        self._list_shadow = list_shadow
        self.list.setUniformItemSizes(False)
        self.list.itemClicked.connect(self._on_item_activated)
        self.list.itemActivated.connect(self._on_item_activated)
        self.list.itemDoubleClicked.connect(self._on_item_double_clicked)
        root.addWidget(self.list, 1)
        esc = QShortcut(QKeySequence("Esc"), self)
        esc.activated.connect(self.hide)
        self.empty_label = QLabel()
        self.empty_label.setObjectName("countLabel")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setWordWrap(True)
        root.addWidget(self.empty_label)

        foot = QHBoxLayout()
        self.count_label = QLabel()
        self.count_label.setObjectName("countLabel")
        foot.addWidget(self.count_label)
        foot.addStretch(1)
        self.pause_btn = QPushButton()
        self.pause_btn.clicked.connect(self.toggle_pause)
        foot.addWidget(self.pause_btn)
        self.clear_btn = QPushButton()
        self.clear_btn.setObjectName("dangerBtn")
        self.clear_btn.clicked.connect(self.clear_all)
        foot.addWidget(self.clear_btn)
        self.settings_btn = QPushButton()
        self.settings_btn.clicked.connect(self.open_settings)
        foot.addWidget(self.settings_btn)
        root.addLayout(foot)

        self.hotkey_label = QLabel()
        self.hotkey_label.setObjectName("countLabel")
        root.addWidget(self.hotkey_label)

    def _build_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(QIcon(asset_path("icon.png")), self)
        self.tray.setToolTip(APP_NAME_EN)
        menu = QMenu()
        self.act_open = QAction(self)
        self.act_open.triggered.connect(self.show_panel)
        menu.addAction(self.act_open)
        self.act_pause = QAction(self)
        self.act_pause.triggered.connect(self.toggle_pause)
        menu.addAction(self.act_pause)
        self.act_new_set = QAction(self)
        self.act_new_set.triggered.connect(self.start_new_set)
        menu.addAction(self.act_new_set)
        menu.addSeparator()
        self.act_settings = QAction(self)
        self.act_settings.triggered.connect(self.open_settings)
        menu.addAction(self.act_settings)
        self.act_about = QAction(self)
        self.act_about.triggered.connect(self.show_about)
        menu.addAction(self.act_about)
        menu.addSeparator()
        self.act_quit = QAction(self)
        self.act_quit.triggered.connect(self.quit_app)
        menu.addAction(self.act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        self.retranslate()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_panel()

    # ---------- theme ----------
    def apply_theme(self):
        """Re-skin the whole app for settings["theme"], instantly.

        Swaps the application stylesheet, re-colours the drop shadows
        and the status text, and rebuilds the history rows so the kind
        badges / accent bars pick up the new theme's colours.
        """
        self.theme = get_theme(self.settings.get("theme", "dark"))
        self.app_ref.setStyleSheet(self.theme["qss"])
        if hasattr(self, "_top_shadow"):
            self._top_shadow.setColor(QColor(*self.theme["shadow_top"]))
            self._top_shadow.setBlurRadius(self.theme["shadow_top_blur"])
            self._top_shadow.setOffset(0, self.theme["shadow_top_dy"])
            self._list_shadow.setColor(QColor(*self.theme["shadow_list"]))
            self._list_shadow.setBlurRadius(self.theme["shadow_list_blur"])
            self._list_shadow.setOffset(0, self.theme["shadow_list_dy"])
        self._update_status()
        self.refresh_list()

    # ---------- texts ----------
    def retranslate(self):
        self.lang = self.settings["language"]
        rtl = self.lang in RTL_LANGS
        self.app_ref.setLayoutDirection(
            Qt.RightToLeft if rtl else Qt.LeftToRight)
        self.sub_label.setText(self.tt("app_subtitle"))
        self.search_edit.setPlaceholderText(self.tt("search_placeholder"))
        self.chip_buttons[None].setText(self.tt("tab_all"))
        for kind in KINDS:
            self.chip_buttons[kind].setText(self.tt("kind_" + kind))
        self.set_label.setText(self.tt("set_label"))
        self.new_set_btn.setText(self.tt("new_set"))
        self.rename_btn.setText(self.tt("rename"))
        self.clear_btn.setText(self.tt("clear_all"))
        self.settings_btn.setText(self.tt("settings"))
        if sys.platform == "win32":
            self.hotkey_label.setText("%s · %s" % (
                self.tt("hotkey_hint"), self.tt("kb_hint")))
        else:
            self.hotkey_label.setText(self.tt("kb_hint"))
        self._update_status()
        if self.tray is not None:
            self.act_open.setText(self.tt("tray_open"))
            self.act_pause.setText(
                self.tt("tray_resume" if self.settings["paused"]
                        else "tray_pause"))
            self.act_new_set.setText(self.tt("tray_new_set"))
            self.act_settings.setText(self.tt("tray_settings"))
            self.act_about.setText(self.tt("about"))
            self.act_quit.setText(self.tt("tray_quit"))

    def _update_status(self):
        paused = self.settings["paused"]
        self.status_label.setText(
            "⏸ %s" % self.tt("status_paused") if paused
            else "● %s" % self.tt("status_recording"))
        self.status_label.setStyleSheet(
            "color:%s;" % (self.theme["status_paused"] if paused
                           else self.theme["status_recording"]))
        self.pause_btn.setText(
            self.tt("tray_resume" if paused else "tray_pause"))

    # ---------- list / filtering ----------
    def _set_filter(self, kind):
        self._filter_kind = kind
        self.refresh_list()

    def _on_set_changed(self, _idx):
        self._selected_set = self.set_combo.currentData()
        self.refresh_list()

    def refresh_all(self):
        self._refresh_set_combo()
        self.refresh_list()

    def _refresh_set_combo(self):
        current = self._selected_set
        self.set_combo.blockSignals(True)
        self.set_combo.clear()
        self.set_combo.addItem(self.tt("all_sets"), None)
        for s in reversed(self.store.sets):
            n = len(self.store.items_in_set(s["id"]))
            self.set_combo.addItem("%s (%d)" % (s["name"], n), s["id"])
        idx = 0
        if current is not None:
            for i in range(self.set_combo.count()):
                if self.set_combo.itemData(i) == current:
                    idx = i
                    break
            else:
                self._selected_set = None
        self.set_combo.setCurrentIndex(idx)
        self.set_combo.blockSignals(False)
        self.rename_btn.setEnabled(self._selected_set is not None)

    def _visible_items(self):
        query = self.search_edit.text().strip().lower()
        out = []
        for item in reversed(self.store.items):
            if self._selected_set is not None \
                    and item["set_id"] != self._selected_set:
                continue
            if self._filter_kind is not None \
                    and item["kind"] != self._filter_kind:
                continue
            if query and query not in item["text"].lower():
                continue
            out.append(item)
        return out

    def refresh_list(self):
        items = self._visible_items()
        self.list.clear()
        # Group consecutive items under a work-set header (name, time
        # span, count) so the panel reads as time-ordered work blocks.
        groups = []
        for item in items:
            if groups and groups[-1][0] == item["set_id"]:
                groups[-1][1].append(item)
            else:
                groups.append((item["set_id"], [item]))
        for set_id, group_items in groups:
            s = self.store.get_set(set_id)
            name = s["name"] if s else ""
            first = time.localtime(group_items[-1]["ts"])
            last = time.localtime(group_items[0]["ts"])
            if time.strftime("%m/%d", first) == time.strftime("%m/%d", last):
                span = "%s %s–%s" % (
                    time.strftime("%m/%d", last),
                    time.strftime("%H:%M", first),
                    time.strftime("%H:%M", last))
            else:
                span = "%s – %s" % (
                    time.strftime("%m/%d %H:%M", first),
                    time.strftime("%m/%d %H:%M", last))
            header = SetHeader(self, name, span, len(group_items))
            li = QListWidgetItem()
            li.setData(Qt.UserRole, ("header", set_id))
            li.setFlags(Qt.ItemIsEnabled)  # not selectable: keys skip it
            li.setSizeHint(header.sizeHint())
            self.list.addItem(li)
            self.list.setItemWidget(li, header)
            for item in group_items:
                li = QListWidgetItem()
                li.setData(Qt.UserRole, ("item", item["id"]))
                row = ItemRow(self, item)
                li.setSizeHint(row.sizeHint())
                self.list.addItem(li)
                self.list.setItemWidget(li, row)
        self.count_label.setText(self.tt("count_fmt", count=len(items)))
        self.empty_label.setText(
            self.tt("empty_label") if not self.store.items else "")
        self.empty_label.setVisible(not self.store.items)

    # ---------- actions ----------
    def _item_from_list_item(self, li):
        if li is None:
            return None
        data = li.data(Qt.UserRole)
        if not data or data[0] != "item":
            return None
        for item in self.store.items:
            if item["id"] == data[1]:
                return item
        return None

    def _on_item_activated(self, li):
        item = self._item_from_list_item(li)
        if item is not None:
            self.restore_item(item)

    def _on_item_double_clicked(self, li):
        item = self._item_from_list_item(li)
        if item is not None:
            self.show_detail(item)

    def show_detail(self, item):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tt("detail_title"))
        dlg.resize(520, 340)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        lt = time.localtime(item["ts"])
        meta = QLabel("%s · %s · %s" % (
            self.tt("kind_" + item["kind"]),
            time.strftime("%Y/%m/%d %H:%M", lt),
            self.tt("reason_" + item["reason"])))
        meta.setObjectName("rowMeta")
        lay.addWidget(meta)
        body = QPlainTextEdit()
        body.setReadOnly(True)
        body.setPlainText(item["text"])
        lay.addWidget(body, 1)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        restore_btn = QPushButton(self.tt("restore_btn"))
        restore_btn.setObjectName("accentBtn")
        restore_btn.clicked.connect(
            lambda: (dlg.accept(), self.restore_item(item)))
        btn_row.addWidget(restore_btn)
        close_btn = QPushButton(self.tt("ok"))
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)
        dlg.exec()

    def restore_item(self, item):
        self._setting_clipboard = True
        try:
            QApplication.clipboard().setText(item["text"])
        except Exception:
            self._setting_clipboard = False
            return
        QTimer.singleShot(600, self._clear_clipboard_flag)
        self.hide()
        if self.tray is not None:
            self.tray.showMessage(APP_NAME_EN, self.tt("restored_hint"),
                                  QSystemTrayIcon.Information, 1600)

    def _clear_clipboard_flag(self):
        self._setting_clipboard = False

    def toggle_pin(self, item_id):
        for i in self.store.items:
            if i["id"] == item_id:
                self.store.set_pinned(item_id, not i["pinned"])
                break
        self._save_soon()
        self.refresh_list()

    def delete_item(self, item_id):
        box = QMessageBox(self)
        box.setWindowTitle(self.tt("delete_item"))
        box.setText(self.tt("delete_confirm"))
        ok_b = box.addButton(self.tt("ok"), QMessageBox.AcceptRole)
        box.addButton(self.tt("cancel"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not ok_b:
            return
        self.store.delete_item(item_id)
        self._save_soon()
        self.refresh_all()

    def clear_all(self):
        box = QMessageBox(self)
        box.setWindowTitle(self.tt("clear_all_title"))
        box.setText(self.tt("clear_all_confirm"))
        ok_b = box.addButton(self.tt("ok"), QMessageBox.AcceptRole)
        box.addButton(self.tt("cancel"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is ok_b:
            self.store.clear_all()
            self._selected_set = None
            self._save_soon()
            self.refresh_all()

    def start_new_set(self):
        self.store.start_set()
        self._selected_set = self.store.current_set_id
        self._save_soon()
        self.refresh_all()

    def rename_current_set(self):
        if self._selected_set is None:
            return
        s = self.store.get_set(self._selected_set)
        if s is None:
            return
        name, ok = QInputDialog.getText(
            self, self.tt("rename_title"), self.tt("rename_prompt"),
            text=s["name"])
        if ok and name.strip():
            self.store.rename_set(s["id"], name.strip())
            self._save_soon()
            self._refresh_set_combo()

    def toggle_pause(self):
        self.settings["paused"] = not self.settings["paused"]
        self._save_soon()
        self._update_status()
        self.retranslate()

    def open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec() == QDialog.Accepted:
            old_lang = self.settings["language"]
            old_theme = self.settings["theme"]
            dlg.apply_to(self.settings)
            self.store.gap_seconds = self.settings["gap_minutes"] * 60
            set_autostart(self.settings["autostart"])
            self._save_now()
            self._run_expire()
            if self.settings["theme"] != old_theme:
                self.apply_theme()
            if self.settings["language"] != old_lang:
                self.retranslate()
                self.refresh_all()
            else:
                self._update_status()
                self.refresh_all()

    def show_about(self):
        box = QMessageBox(self)
        box.setWindowTitle(self.tt("about"))
        box.setIconPixmap(QIcon(asset_path("icon.png")).pixmap(64, 64))
        box.setText("%s  %s\n%s\n\n%s" % (
            APP_NAME_EN, VERSION, APP_NAME_JA, self.tt("about_body")))
        box.setStandardButtons(QMessageBox.Ok)
        box.button(QMessageBox.Ok).setText(self.tt("ok"))
        box.exec()

    # ---------- panel visibility ----------
    def show_panel(self):
        self._run_expire()
        self.refresh_all()
        if not self.isVisible():
            screen = QApplication.screenAt(QCursor.pos()) \
                or QApplication.primaryScreen()
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_edit.setFocus()

    def toggle_panel(self):
        if self.isVisible():
            self.hide()
        else:
            self.show_panel()

    def closeEvent(self, event):
        # Closing the window only hides it; the app stays in the tray.
        event.ignore()
        self.hide()

    # ---------- clipboard ----------
    def on_clipboard_changed(self):
        if self._setting_clipboard:
            self._setting_clipboard = False
            return
        if self.settings["paused"]:
            return
        try:
            text = QApplication.clipboard().text()
        except Exception:
            return
        if not text or not text.strip():
            return
        if len(text) > MAX_STORED_TEXT:
            return
        if self.settings["block_sensitive"]:
            sens = is_sensitive(text)
            if sens:
                now = time.time()
                if now - self._last_block_notice > 10 and self.tray is not None:
                    self._last_block_notice = now
                    key = "blocked_card" if sens == "card" else "blocked_secret"
                    self.tray.showMessage(APP_NAME_EN, self.tt(key),
                                          QSystemTrayIcon.Information, 2000)
                return
        kind, reason = classify(text)
        item = self.store.add(text, kind, reason)
        if item is not None:
            self._housekeep()
            self._save_soon()
            if self.isVisible():
                self.refresh_all()

    def quit_app(self):
        self._save_now()
        try:
            self.hotkey.stop()
        except Exception:
            pass
        QApplication.quit()


def main():
    if getattr(sys, "frozen", False):
        # Packaged (PyInstaller) starts reach Qt initialisation much
        # faster than source starts; under Wine that intermittently
        # raced the session services at startup (Qt6Core page fault
        # within the first seconds, ~half of launches). A short settle
        # pause before creating the QApplication avoids the window.
        time.sleep(3)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME_EN)
    app.setApplicationVersion(VERSION)
    app.setQuitOnLastWindowClosed(False)
    load_app_fonts()
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSizeF(10.5)
    app.setFont(font)
    app.setStyleSheet(get_theme(load_settings()["theme"])["qss"])
    panel = Panel(app)
    # A manual launch opens the panel (like the sibling apps); the
    # autostart entry passes --tray to start quietly in the tray.
    # The first show is deferred a moment so the event loop is already
    # running when the window appears (startup robustness).
    if "--tray" not in sys.argv:
        QTimer.singleShot(600, panel.show_panel)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Offscreen UI smoke tests: panel builds, clipboard flow, filtering,
robustness against empty / huge / weird input. Run with
QT_QPA_PLATFORM=offscreen."""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as appmod


def _make_panel(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "config_dir",
                        lambda: str(tmp_path))
    monkeypatch.setattr(appmod, "settings_path",
                        lambda: os.path.join(str(tmp_path), "settings.json"))
    monkeypatch.setattr(appmod, "history_path",
                        lambda: os.path.join(str(tmp_path), "history.json"))
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])
    qapp.setQuitOnLastWindowClosed(False)
    panel = appmod.Panel(qapp)
    return qapp, panel


def test_panel_builds_and_records(tmp_path, monkeypatch):
    qapp, panel = _make_panel(tmp_path, monkeypatch)
    from PySide6.QtWidgets import QApplication
    QApplication.clipboard().setText("https://example.com/test")
    qapp.processEvents()
    assert len(panel.store.items) == 1
    assert panel.store.items[0]["kind"] == "url"
    QApplication.clipboard().setText("¥12,800")
    qapp.processEvents()
    assert len(panel.store.items) == 2
    assert panel.store.items[1]["kind"] == "amount"
    panel.quit_app()


def test_sensitive_blocked_by_default(tmp_path, monkeypatch):
    qapp, panel = _make_panel(tmp_path, monkeypatch)
    from PySide6.QtWidgets import QApplication
    QApplication.clipboard().setText("4111 1111 1111 1111")
    qapp.processEvents()
    assert len(panel.store.items) == 0
    panel.quit_app()


def test_pause_blocks_recording(tmp_path, monkeypatch):
    qapp, panel = _make_panel(tmp_path, monkeypatch)
    from PySide6.QtWidgets import QApplication
    panel.settings["paused"] = True
    QApplication.clipboard().setText("hello world")
    qapp.processEvents()
    assert len(panel.store.items) == 0
    panel.quit_app()


def test_robust_inputs(tmp_path, monkeypatch):
    qapp, panel = _make_panel(tmp_path, monkeypatch)
    from PySide6.QtWidgets import QApplication
    for weird in ["", "   ", "\n\n", "🎉" * 50, "a" * 99999,
                  "<script>alert(1)</script>", "\x00\x01", "日本語　テスト"]:
        QApplication.clipboard().setText(weird)
        qapp.processEvents()
    # empty/whitespace are skipped; the rest must not crash anything
    panel.refresh_all()
    panel.quit_app()


def _rows(panel):
    """(headers, items) among the list rows, via the UserRole marker."""
    from PySide6.QtCore import Qt
    headers = items = 0
    for i in range(panel.list.count()):
        data = panel.list.item(i).data(Qt.UserRole)
        if data and data[0] == "header":
            headers += 1
        elif data and data[0] == "item":
            items += 1
    return headers, items


def test_filter_and_search(tmp_path, monkeypatch):
    qapp, panel = _make_panel(tmp_path, monkeypatch)
    panel.store.add("https://a.example", "url", "url", ts=time.time())
    panel.store.add("taro@example.com", "email", "email",
                    ts=time.time() + 1)
    panel.refresh_all()
    # one work-set header row + two item rows
    assert _rows(panel) == (1, 2)
    panel._set_filter("email")
    assert _rows(panel) == (1, 1)
    panel._set_filter(None)
    panel.search_edit.setText("taro@")
    panel.refresh_list()
    assert _rows(panel) == (1, 1)
    panel.quit_app()


def test_set_headers_group_items(tmp_path, monkeypatch):
    qapp, panel = _make_panel(tmp_path, monkeypatch)
    now = time.time()
    panel.store.add("https://a.example", "url", "url", ts=now)
    panel.store.start_set()
    panel.store.add("¥3,000", "amount", "amount_symbol", ts=now + 1)
    panel.refresh_all()
    assert _rows(panel) == (2, 2)  # two sets -> two headers
    panel.quit_app()


def test_delete_needs_confirmation(tmp_path, monkeypatch):
    qapp, panel = _make_panel(tmp_path, monkeypatch)
    from PySide6.QtWidgets import QMessageBox
    panel.store.add("https://a.example", "url", "url", ts=time.time())
    item_id = panel.store.items[0]["id"]
    # Cancel path: clickedButton() -> None keeps the item.
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda self: None)
    panel.delete_item(item_id)
    assert len(panel.store.items) == 1
    # OK path: clickedButton() returns the accept-role button object.
    sentinel = object()
    monkeypatch.setattr(QMessageBox, "addButton",
                        lambda self, *a, **k: sentinel)
    monkeypatch.setattr(QMessageBox, "clickedButton",
                        lambda self: sentinel)
    panel.delete_item(item_id)
    assert len(panel.store.items) == 0
    panel.quit_app()


def test_enter_activation_restores(tmp_path, monkeypatch):
    qapp, panel = _make_panel(tmp_path, monkeypatch)
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    panel.store.add("https://enter.example", "url", "url",
                    ts=time.time())
    panel.refresh_all()
    for i in range(panel.list.count()):
        li = panel.list.item(i)
        if li.data(Qt.UserRole) and li.data(Qt.UserRole)[0] == "item":
            panel._on_item_activated(li)
            break
    assert QApplication.clipboard().text() == "https://enter.example"
    panel.quit_app()


def test_detail_dialog_builds(tmp_path, monkeypatch):
    qapp, panel = _make_panel(tmp_path, monkeypatch)
    from PySide6.QtWidgets import QDialog
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    panel.store.add("x" * 500, "other", "long", ts=time.time())
    panel.show_detail(panel.store.items[0])  # must not raise / block
    panel.quit_app()


def test_language_switch_all(tmp_path, monkeypatch):
    qapp, panel = _make_panel(tmp_path, monkeypatch)
    from i18n_data import LANG_ORDER
    for lang in LANG_ORDER:
        panel.settings["language"] = lang
        panel.retranslate()
        panel.refresh_all()
    panel.quit_app()

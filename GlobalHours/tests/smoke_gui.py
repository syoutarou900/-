# -*- coding: utf-8 -*-
"""Offscreen GUI smoke test + screenshot capture (band design).

Run: QT_QPA_PLATFORM=offscreen python3 tests/smoke_gui.py
Builds the main window with sample partners, checks the band rows,
candidate chips and proposal, switches ja -> de -> ar (RTL) and
saves screenshots to build-work/shots/.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("XDG_CONFIG_HOME", "/tmp/tzchecker-smoke")

from PySide6.QtCore import QDate, QEvent
from PySide6.QtWidgets import QApplication

import app as app_module
import theme
from tzcore import AppState, OwnSettings, Partner

SHOTS = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "build-work", "shots")
os.makedirs(SHOTS, exist_ok=True)


def grab(qapp, win, name):
    """Save a screenshot after fully settling the window: rebuilt
    widgets are removed via deleteLater, so flush deferred deletions
    and repaint first — otherwise the capture can show ghost widgets
    from the previous language/theme."""
    qapp.processEvents()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    win.repaint()
    qapp.processEvents()
    win.grab().save(os.path.join(SHOTS, name))


def main():
    qapp = QApplication(sys.argv)
    theme.apply_theme(qapp)
    state = AppState(
        own=OwnSettings(zone="Asia/Tokyo", country_code="JP"),
        partners=[
            Partner(name="New York Office", country_code="US",
                    city="New York", zone="America/New_York"),
            Partner(name="London Office", country_code="GB",
                    city="London", zone="Europe/London"),
            Partner(name="Singapore Office", country_code="SG",
                    city="Singapore", zone="Asia/Singapore"),
        ],
        lang="ja")
    win = app_module.MainWindow(state)
    win.resize(1280, 880)
    win.show()
    qapp.processEvents()

    assert len(win._partner_rows) == 3, "band rows"
    # a weekday daytime makes the bands show their full colours
    from PySide6.QtCore import QDateTime, QTime
    win.dt_edit.setDateTime(QDateTime(QDate(2026, 1, 19), QTime(17, 0)))
    # select Singapore (index 2): slots exist on business days
    win._select_partner(2)
    win.slot_date.setDate(QDate(2026, 1, 19))   # Monday
    win.refresh_slots()
    qapp.processEvents()
    assert len(win._slots) > 0, "candidate slots for Singapore"
    assert win.chips_layout.count() == len(win._slots)
    # chip click fills the proposal and copies it
    win._chip_clicked(win._slots[0])
    assert "Singapore" in win.proposal_edit.toPlainText()
    grab(qapp, win, "shot-ja.png")

    for lang, name in (("de", "shot-de.png"), ("ar", "shot-ar.png")):
        idx = win.lang_combo.findData(lang)
        win.lang_combo.setCurrentIndex(idx)
        qapp.processEvents()
        assert win.lang == lang
        # edit buttons must fit their (possibly long) labels
        from PySide6.QtGui import QFontMetrics as _QFM
        for row in [win.own_row] + list(win._partner_rows):
            need = (_QFM(row.edit_btn.font()).horizontalAdvance(
                row.edit_btn.text()) + 24)
            assert row.edit_btn.width() >= need, (
                f"edit button clipped in {lang}: "
                f"{row.edit_btn.width()} < {need}")
        grab(qapp, win, name)

    # chips: every chip must be wide enough for its full text
    from PySide6.QtGui import QFontMetrics
    for i in range(win.chips_layout.count()):
        chip = win.chips_layout.itemAt(i).widget()
        need = (QFontMetrics(chip.font()).horizontalAdvance(chip.text())
                + 30)
        assert chip.width() >= need, (
            f"chip text clipped: {chip.text()!r} "
            f"{chip.width()} < {need}")
        assert chip.height() == 44

    # theme toggle: dark -> light in place, choice saved, then back
    import theme as theme_mod
    assert win.theme_name == "dark"
    win._toggle_theme()
    qapp.processEvents()
    assert win.theme_name == "light" and state.theme == "light"
    assert theme_mod.current_name() == "light"
    assert "#EFF4FC" in qapp.styleSheet()
    for lang, name in (("ja", "shot-light-ja.png"),
                       ("de", "shot-light-de.png"),
                       ("ar", "shot-light-ar.png")):
        idx = win.lang_combo.findData(lang)
        win.lang_combo.setCurrentIndex(idx)
        qapp.processEvents()
        assert win.lang == lang
        grab(qapp, win, name)
    win._toggle_theme()
    qapp.processEvents()
    assert win.theme_name == "dark" and state.theme == "dark"

    # overlay dialogs construct
    from app import PartnerDialog, OwnSettingsDialog
    dlg = PartnerDialog("ja", parent=win)
    assert dlg.result_partner().zone
    dlg.close()
    odlg = OwnSettingsDialog("ja", state.own, parent=win)
    assert odlg.result_own().zone == "Asia/Tokyo"
    odlg.close()

    print("SMOKE OK", sorted(os.listdir(SHOTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

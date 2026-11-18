# -*- coding: utf-8 -*-
"""Offscreen GUI smoke test: launch, load sample, type a correct value and a
digit-mismatch, capture screenshots. Run with QT_QPA_PLATFORM=offscreen."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication

import core
from app import MainWindow

SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shots")
os.makedirs(SHOTS, exist_ok=True)


def find_row(win, group, field):
    for i, it in enumerate(win.items):
        if it["group"] == group and it["field"] == field:
            return i
    raise AssertionError(f"row not found: {group}/{field}")


def main():
    app = QApplication([])
    win = MainWindow()
    win.resize(1200, 780)
    win.show()
    app.processEvents()

    win.load_items(core.sample_items(), "sample")
    import time
    for _ in range(10):
        app.processEvents()
        time.sleep(0.05)
    assert win.stat_labels["stat_remaining"].text() == "未入力が15件", win.stat_labels["stat_remaining"].text()
    p1 = os.path.join(SHOTS, "01_sample_initial.png")
    win.grab().save(p1)

    # one correct value (text), one correct number, one digit-mismatch number
    i1 = find_row(win, "請求書", "請求番号")
    win.rows[i1]["edit"].setText("INV-2026-001")
    i2 = find_row(win, "ノート A5", "単価")
    win.rows[i2]["edit"].setText("150")
    i3 = find_row(win, "ノート A5", "数量")
    win.rows[i3]["edit"].setText("1")  # source 10 -> digit mismatch
    app.processEvents()

    assert core.compare("INV-2026-001", win.rows[i1]["edit"].text())["status"] == "match"
    assert win.rows[i1]["check_label"].text() == "✓"
    assert win.rows[i3]["reason_label"].text() != ""
    stats_text = win.stat_labels["stat_remaining"].text()
    assert stats_text == "未入力が12件", stats_text
    assert win.stat_labels["stat_mismatch"].text() == "不一致 1"
    assert not win.banner.isVisible()

    p2 = os.path.join(SHOTS, "02_mid_work.png")
    win.grab().save(p2)
    print("SMOKE OK", p1, p2)
    print("remaining:", stats_text, "| mismatch:", win.stat_labels["stat_mismatch"].text())
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Offscreen smoke test for typed key/compare column names.

Drives the real GUI three ways over the same demo tables:
  1. selection-based run (proposal picks, as before),
  2. free-TYPED variants in the key/compare combos (fullwidth space,
     synonym, cross-language, parenthesised unit) -> identical results,
  3. gibberish in key1 -> run stops, localized warning + red border.
Also exercises the cross-side auto-fill of key1 and takes a screenshot
of the setup area with typed text sitting in the key combo.
No QMessageBox is involved anywhere in this flow: the warning surface
is the status label + combo border, which is what we assert on.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from smoke_gui import A_ROWS, B_ROWS, HA, HB  # demo data (test-only)

import core
from core import Table


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    import app as appmod
    win = appmod.MainWindow()
    win.table_a = Table(HA, A_ROWS)
    win.table_b = Table(HB, B_ROWS)
    win._fill_preview(win.prev_a, win.table_a)
    win._fill_preview(win.prev_b, win.table_b)
    win._apply_proposal()
    ka, kb = win.combos[("key1", "a")], win.combos[("key1", "b")]
    assert ka.currentText() == "会社名" and kb.currentText() == "取引先", (
        ka.currentText(), kb.currentText())

    # ---- cross-fill: B cleared (untouched), A edited -> B auto-fills
    kb.setEditText("")
    ka.setEditText("会社　名")                    # fullwidth space variant
    win._on_combo_edited("key1", "a")
    assert kb.currentText() == "取引先", kb.currentText()   # B's own header
    assert win._combo_dirty[("key1", "b")] is False
    # ... but never when B was hand-edited by the user
    win._on_text_typed("key1", "b")
    kb.setEditText("zzz")
    win._on_combo_edited("key1", "a")
    assert kb.currentText() == "zzz"
    win._combo_dirty[("key1", "b")] = False       # reset for the runs below

    # ---- 1. selection-based run
    ka.setEditText("会社名")
    kb.setEditText("取引先")
    win._run()
    assert win.result is not None
    counts_sel = win.result.counts()
    print("selection counts:", counts_sel)

    # ---- 2. typed-variant run -> identical categories
    ka.setEditText("会社　名")                    # fullwidth space
    kb.setEditText("取引先名")                    # synonym
    win.combos[("cmp1", "a")].setEditText("数量（個）")
    win.combos[("cmp1", "b")].setEditText("Qty")  # cross-language
    win.combos[("cmp2", "a")].setEditText("金額（円）")
    win.combos[("cmp2", "b")].setEditText("amount（円）")
    win.result = None
    win._run()
    assert win.result is not None
    counts_typed = win.result.counts()
    print("typed counts:    ", counts_typed)
    assert counts_typed == counts_sel, (counts_sel, counts_typed)
    assert win.result_cfg["key_pairs"] == [(1, 1)]
    assert sorted(win.result_cfg["compare_pairs"]) == [(2, 2), (3, 3)]

    # ---- 3. gibberish -> blocked run, localized warning, red border
    win.result = None
    ka.setEditText("zzzqqq")
    win._run()
    assert win.result is None
    expect = win.t("col_unresolved", text="zzzqqq")
    assert win.status_label.text() == expect, win.status_label.text()
    assert "#dc2626" in ka.styleSheet()
    print("warning shown: ", win.status_label.text())
    # fixing the text and re-validating clears the mark
    ka.setEditText("会社　名")
    kb.setEditText("取引先")
    win._on_combo_edited("key1", "a")
    assert ka.styleSheet() == ""
    win._run()
    assert win.result is not None and win.result.counts() == counts_sel

    # ---- screenshot: setup area with the typed variant in key1
    win.show()
    app.processEvents()
    pt = ka.mapTo(win, QPoint(0, 0))
    rect = QRect(max(0, pt.x() - 200), max(0, pt.y() - 48),
                 min(980, win.width()), 260)
    out = os.path.join(os.path.dirname(__file__), "..", "shots")
    os.makedirs(out, exist_ok=True)
    shot = os.path.join(out, "04_typed_setup.png")
    win.grab(rect).save(shot)
    print("SMOKE TYPED OK", os.path.abspath(shot))


if __name__ == "__main__":
    main()

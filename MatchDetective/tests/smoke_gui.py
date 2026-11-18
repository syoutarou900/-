# -*- coding: utf-8 -*-
"""Offscreen smoke test: builds a realistic reconciliation demo inside the
test (NOT shipped with the app), drives the real GUI, and screenshots the
3-category results and the category-3 candidate view."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import core
from core import Table

HA = ["注文番号", "会社名", "金額", "数量"]
A_ROWS = [
    ["PO-1001", "株式会社サンプル商事", "120,000", "30"],
    ["PO-1002", "グローバル貿易", "85,500", "12"],
    ["PO-1003", "タナカ電機（株）", "46,200", "7"],
    ["PO-1004", "北海フーズ合同会社", "33,000", "50"],
    ["PO-1005", "ミドリ印刷", "18,900", "100"],
    ["PO-1006", "アオイ物流", "250,000", "3"],
    ["PO-1007", "山川製作所", "64,000", "8"],
]
HB = ["納品番号", "取引先", "金額", "数量"]
B_ROWS = [
    ["DN-501", "サンプル商事 (株)", "120,000", "30"],
    ["DN-502", "グローバル貿易商事", "85,500", "12"],
    ["DN-503", "タナカ電機株式会社", "46,200", "7"],
    ["DN-504", "北海フーズ (同)", "30,000", "50"],
    ["DN-505", "ミドリ印刷", "9,450", "50"],
    ["DN-506", "ミドリ印刷", "9,450", "50"],
    ["DN-507", "西日本パーツ", "77,000", "20"],
]


def main():
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    import app as appmod
    win = appmod.MainWindow()
    win.table_a = Table(HA, A_ROWS)
    win.table_b = Table(HB, B_ROWS)
    win._fill_preview(win.prev_a, win.table_a)
    win._fill_preview(win.prev_b, win.table_b)
    win.card_a["info"].setText("orders.csv (7 rows)")
    win.card_b["info"].setText("deliveries.csv (7 rows)")
    win._apply_proposal()
    # key: company; compare: amount + qty (exercises every phase)
    win.result = core.reconcile(
        win.table_a, win.table_b, [(1, 1)], [(2, 2), (3, 3)])
    win.result_cfg = {"key_pairs": [(1, 1)],
                      "compare_pairs": [(2, 2), (3, 3)],
                      "tolerance": core.Decimal("0")}
    win._refresh_results()
    win._refresh_summary()
    win.show()
    app.processEvents()
    out = os.path.join(os.path.dirname(__file__), "..", "shots")
    os.makedirs(out, exist_ok=True)
    win.tabs.setCurrentIndex(0)
    app.processEvents()
    win.grab().save(os.path.join(out, "01_cat1.png"))
    win.tabs.setCurrentIndex(2)
    app.processEvents()
    win.grab().save(os.path.join(out, "02_cat3_candidates.png"))
    win.tabs.setCurrentIndex(1)
    app.processEvents()
    win.grab().save(os.path.join(out, "03_cat2.png"))
    c = win.result.counts()
    print("counts:", c)
    for cand in win.result.candidates:
        print("cand:", cand.kind, cand.reason_key, cand.confidence, cand.status)
    print("SMOKE OK", os.path.abspath(out))


if __name__ == "__main__":
    main()

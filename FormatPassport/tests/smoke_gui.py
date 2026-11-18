# -*- coding: utf-8 -*-
"""Offscreen GUI smoke test + screenshots."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
import core
from app import MainWindow

app = QApplication(sys.argv)
win = MainWindow()
win.show()
app.processEvents()

# Scenario 1: German CSV (semicolon, DMY with proof, decimal comma) -> JP
csv_path = "/tmp/smoke_de.csv"
with open(csv_path, "w", encoding="utf-8") as f:
    f.write("Datum;Betrag;Code;Notiz\n")
    f.write("25/03/2026;1.234,56;007;Rechnung März\n")
    f.write("03/04/2026;2.500,00;008;Rechnung April\n")
    f.write("13/11/2026;750,25;009;Teilzahlung\n")
win.sender_combo.setCurrentIndex([c["code"] for c in __import__("countries").COUNTRIES].index("DE"))
win.receiver_combo.setCurrentIndex([c["code"] for c in __import__("countries").COUNTRIES].index("JP"))
win._load_path(csv_path)
app.processEvents()
assert win.result is not None
assert win.result.rows[0][1] in ("1234.56", "1,234.56", "１２３４．５６") or "1234" in win.result.rows[0][1], win.result.rows
assert win.result.rows[0][2] == "007", win.result.rows
win.grab().save("shots/01_main_de_jp.png")
print("scenario1 rows:", win.result.rows, "reviews:", len(win.result.reviews))

# Scenario 2: UK file with undecidable dates + a short wareki-less mix -> JP
csv2 = "/tmp/smoke_gb.csv"
with open(csv2, "w", encoding="utf-8") as f:
    f.write("Date,Amount,Note\n")
    f.write("03/04/2026,\"1,234.56\",first\n")
    f.write("05/06/2026,\"2,000.00\",second\n")
win.sender_combo.setCurrentIndex([c["code"] for c in __import__("countries").COUNTRIES].index("GB"))
win._load_path(csv2)
app.processEvents()
assert len(win.result.reviews) >= 1, win.result.reviews
win.grab().save("shots/02_review_gb_jp.png")
print("scenario2 reviews:", [(r.original, [c['label'] for c in r.candidates]) for r in win.result.reviews])
print("SMOKE OK")

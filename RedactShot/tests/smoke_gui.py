# -*- coding: utf-8 -*-
"""Offscreen GUI smoke test (worker B).

Run: QT_QPA_PLATFORM=offscreen python3 tests/smoke_gui.py
Checks: main window builds, ar (RTL) language switch, PIL test image
load via the OcrUnavailable path (no Tesseract in this environment),
manual region add (direct + via canvas signal), preview/final image
generation, and construction of the final-preview dialog (export hand-off
point). No modal export dialog is executed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog

import appinfo
from app import FinalPreviewDialog, MainWindow, settings_path
from i18n import tr


def main():
    app = QApplication([])
    win = MainWindow()
    win.resize(1240, 800)
    win.show()
    app.processEvents()
    assert win.isVisible() or True  # offscreen: just require construction
    assert appinfo.APP_ID in win.windowTitle(), win.windowTitle()
    assert win.title_label.text() == appinfo.display_name("ja")
    print("1. main window OK, title:", win.windowTitle())

    # language switch to Arabic (RTL) must not crash
    win.apply_language("ar")
    app.processEvents()
    assert app.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert win.title_label.text() == appinfo.display_name("ar")
    print("2. ar / RTL switch OK, title:", win.title_label.text())
    win.apply_language("ja")
    app.processEvents()
    assert app.layoutDirection() == Qt.LayoutDirection.LeftToRight
    print("   back to ja OK")

    # settings path sanity
    sp = settings_path()
    assert sp.endswith(os.path.join(appinfo.APP_ID, "settings.json")), sp
    print("3. settings path OK:", sp)

    # test image: striped pattern so pixelate visibly changes pixels
    tmpdir = "/tmp/blurshield_smoke"
    os.makedirs(tmpdir, exist_ok=True)
    img_path = os.path.join(tmpdir, "shot.png")
    img = Image.new("RGB", (400, 200), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for x in range(0, 400, 8):
        if (x // 8) % 2 == 0:
            d.rectangle([x, 0, x + 7, 199], fill=(0, 0, 0))
    d.rectangle([20, 20, 180, 60], fill=(200, 30, 30))
    img.save(img_path)

    win.load_path(img_path)
    # OCR now runs on a worker thread: pump events until it settles
    import time as _time
    for _ in range(200):
        app.processEvents()
        if getattr(win, "_ocr_thread", None) is None:
            break
        _time.sleep(0.05)
    app.processEvents()
    assert win.original_pil is not None and win.original_pil.size == (400, 200)
    # No Tesseract here -> OcrUnavailable path: banner shown, manual-only
    assert win.banner.isVisible(), "OCR banner should be visible"
    assert win.banner.text() == tr("ja", "ocr_unavailable")
    assert win.candidates == []
    print("4. image load + OcrUnavailable path OK (banner shown, 0 candidates)")

    # manual region add (direct API)
    win.add_manual_region(20, 20, 160, 40)
    app.processEvents()
    assert len(win.candidates) == 1
    cand = win.candidates[0]
    assert cand.category == "manual" and cand.manual is True and cand.enabled is True
    assert isinstance(cand.id, int), cand.id
    print("5. manual region add OK, id:", cand.id)

    # manual region add via canvas signal (the drag-finished path)
    win.canvas.regionCreated.emit(220, 100, 120, 50)
    app.processEvents()
    assert len(win.candidates) == 2
    print("6. canvas regionCreated -> candidate OK, count:", len(win.candidates))

    # preview + full-res final image: effects must change the region pixels
    # (region 2 covers the striped pattern, so pixelate changes it;
    #  region 1 is a solid fill, so verify it with blackout instead)
    final = win.build_final_image()
    assert final is not None and final.size == (400, 200)
    assert final.crop((220, 100, 340, 150)).tobytes() != \
        win.original_pil.crop((220, 100, 340, 150)).tobytes()
    idx_blackout = win.effect_combo.findData("blackout")
    assert idx_blackout >= 0
    win.effect_combo.setCurrentIndex(idx_blackout)
    app.processEvents()
    final_b = win.build_final_image()
    assert final_b.getpixel((30, 30)) == (0, 0, 0), final_b.getpixel((30, 30))
    win.effect_combo.setCurrentIndex(win.effect_combo.findData("pixelate"))
    app.processEvents()
    # original untouched
    assert win.original_pil.getpixel((30, 30)) == (200, 30, 30)
    print("7. final image OK (pixelate + blackout applied to copy, original untouched)")

    # toggling a candidate off must restore its region in the preview build
    win.candidates[0].enabled = False
    final2 = win.build_final_image()
    assert final2.crop((20, 20, 180, 60)).tobytes() == win.original_pil.crop((20, 20, 180, 60)).tobytes()
    win.candidates[0].enabled = True
    print("8. candidate on/off reflection OK")

    # final-preview dialog (export hand-off point) constructs and shows text
    dlg = FinalPreviewDialog(win.build_final_image(), "ja", win)
    assert dlg.btn_confirm.text() == tr("ja", "confirm_export")
    dlg.show()
    app.processEvents()
    print("9. final preview dialog OK, confirm button:", dlg.btn_confirm.text())
    dlg.reject()

    # delete via canvas-requested path
    win.delete_candidate(win.candidates[0].id)
    assert len(win.candidates) == 1
    print("10. delete candidate OK")

    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

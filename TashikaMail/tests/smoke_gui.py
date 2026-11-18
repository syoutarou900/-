# -*- coding: utf-8 -*-
"""GUI smoke test + screenshots (offscreen). Workspace-scoped only."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from PySide6.QtWidgets import QApplication

import app as app_module
import core

DEMO_DIR = os.path.join("shots", "demo")
os.makedirs(DEMO_DIR, exist_ok=True)

BODY_OK = """Dear Alphacorp team,

Please find the invoice attached.
Invoice No. INV-1001
Date: 2026/11/14
Payment due: 2026/11/30
Total amount: $1,100.00

Best regards,
Alphacorp Inc."""

ATT_OK = """Invoice
Invoice No. INV-1001
Date: 2026/11/14
Payment due: 2026/11/30
Subtotal $1,000.00
Tax $100.00
Total $1,100.00
Alphacorp Inc."""


def shot(win, name):
    win.repaint()
    pix = win.grab()
    pix.save(os.path.join("shots", name))
    print("saved", name, pix.width(), pix.height())


def run_and_wait(win, qapp):
    import time
    win.report = None
    win.run_check()
    deadline = time.time() + 120
    while time.time() < deadline:
        qapp.processEvents()
        if win.report is not None and win._check_thread is None:
            return
        time.sleep(0.02)
    raise AssertionError("check did not finish in time")


def main():
    qapp = QApplication(sys.argv)
    win = app_module.MainWindow()
    win.show()
    qapp.processEvents()
    shot(win, "main.png")

    att_path = os.path.join(DEMO_DIR, "invoice.txt")
    with open(att_path, "w", encoding="utf-8") as fh:
        fh.write(ATT_OK)
    win.to_edit.setText("taro@alphacorp.co.jp")
    win.subject_edit.setText("Invoice INV-1001")
    win.body_edit.setPlainText(BODY_OK)
    win.attachments = [core.read_attachment(att_path)]
    win._refresh_att_list()
    run_and_wait(win, qapp)
    assert win.report.overall == "green", win.report.overall
    shot(win, "result_green.png")

    bad_path = os.path.join(DEMO_DIR, "invoice_bad.txt")
    with open(bad_path, "w", encoding="utf-8") as fh:
        fh.write(ATT_OK.replace("$1,100.00", "$1,200.00")
                 .replace("INV-1001", "INV-1002"))
    win.attachments = [core.read_attachment(bad_path)]
    win._refresh_att_list()
    run_and_wait(win, qapp)
    assert win.report.overall == "red", win.report.overall
    shot(win, "result_red.png")

    # ---- OCR result screen (provenance badge + caution row) ----
    venv_py = os.path.join(os.path.dirname(__file__), "..", ".venv",
                           "bin", "python")
    dejavu = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    if os.path.exists(venv_py) and os.path.exists(dejavu):
        shim = os.path.join(DEMO_DIR, "tesseract")
        with open(shim, "w", encoding="utf-8") as fh:
            fh.write("#!%s\n" % os.path.abspath(venv_py))
            fh.write(
                "import sys\n"
                "args = sys.argv[1:]\n"
                "langs = args[args.index('-l') + 1]\n"
                "td = args[args.index('--tessdata-dir') + 1]\n"
                "import tesserocr\n"
                "with tesserocr.PyTessBaseAPI(path=td, lang=langs) as api:\n"
                "    api.SetImageFile(args[0])\n"
                "    sys.stdout.write(api.GetUTF8Text())\n")
        os.chmod(shim, 0o755)
        os.environ["TASHIKAMAIL_TESSERACT_CMD"] = shim
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (1654, 1000), "white")
        d = ImageDraw.Draw(img)
        font = ImageFont.truetype(dejavu, 54)
        y = 60
        for line in ("Alphacorp Inc.", "Invoice", "Invoice No. INV-1001",
                     "Date: 2026/11/14", "Payment due: 2026/11/30",
                     "Subtotal $1,000.00", "Tax $100.00", "Total $1,100.00"):
            d.text((80, y), line, fill="black", font=font)
            y += 105
        img_path = os.path.join(DEMO_DIR, "invoice_scan.png")
        img.save(img_path)
        win.attachments = []
        win.add_attachment_paths([img_path])
        run_and_wait(win, qapp)
        assert win.attachments[0].via_ocr, "attachment was not OCR-read"
        assert win.report.overall == "green", win.report.overall
        shot(win, "result_ocr.png")
        print("OCR SCREENSHOT OK")

    # language switching smoke (incl. RTL)
    for lang in ("en", "ar", "ko", "ja"):
        win.apply_language(lang)
        qapp.processEvents()
    print("GUI SMOKE OK")


if __name__ == "__main__":
    main()

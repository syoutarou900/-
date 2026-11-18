# -*- coding: utf-8 -*-
"""OCR integration tests for TashikaMail (たしかめーる).

Two layers:
- resolution tests (fake executables, no real OCR) verify the
  env override > bundled > PATH order, same as TranscribeGuard;
- functional tests run REAL OCR through the app's own code path
  (core.read_attachment -> subprocess tesseract CLI -> bundled
  tessdata_fast) on generated invoice images / scanned PDFs.

On this Linux dev VM the bundled tesseract.exe is a Windows binary, so
the functional tests point TASHIKAMAIL_TESSERACT_CMD at a small shim
that exposes the exact tesseract CLI surface on top of tesserocr
(Tesseract 5.5.4, same engine family) while still using the bundled
tessdata_fast data. On Windows the bundled tesseract.exe 5.5.3 is used
directly. Functional tests skip cleanly when no engine is available.
"""
import email
import email.policy
import os
import sys
import tempfile
import unittest
from decimal import Decimal
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import core  # noqa: E402
import core_checks  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="tashikamail_ocr_test_")
_ENGINE_READY = False

EN_LINES = [
    "Alphacorp Inc.",
    "Invoice",
    "Invoice No. INV-1001",
    "Date: 2026/11/14",
    "Payment due: 2026/11/30",
    "Subtotal $1,000.00",
    "Tax $100.00",
    "Total $1,100.00",
]
JA_LINES = [
    "請求書",
    "株式会社サクラ",
    "請求番号: INV-2001",
    "日付: 2026/11/14",
    "合計 ¥55,000",
]

BODY_OK = """Dear Alphacorp team,

Please find the invoice attached.
Invoice No. INV-1001
Date: 2026/11/14
Payment due: 2026/11/30
Total amount: $1,100.00

Best regards,
Alphacorp Inc."""

BODY_JA = """株式会社サクラ 御中

請求書を送付いたします。
請求番号: INV-2001
日付: 2026/11/14
合計 ¥55,000

よろしくお願いいたします。"""

DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
NOTO = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"


def _write_shim():
    shim = os.path.join(_TMP, "tesseract")
    with open(shim, "w", encoding="utf-8") as fh:
        fh.write("#!%s\n" % sys.executable)
        fh.write(
            "import sys\n"
            "args = sys.argv[1:]\n"
            "langs = args[args.index('-l') + 1] if '-l' in args else 'eng'\n"
            "td = (args[args.index('--tessdata-dir') + 1]\n"
            "      if '--tessdata-dir' in args else None)\n"
            "import tesserocr\n"
            "with tesserocr.PyTessBaseAPI(path=td, lang=langs) as api:\n"
            "    api.SetImageFile(args[0])\n"
            "    sys.stdout.write(api.GetUTF8Text())\n")
    os.chmod(shim, 0o755)
    return shim


def _make_image(lines, font_path, path, font_index=0):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1654, 1000), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, 54, index=font_index)
    y = 60
    for line in lines:
        d.text((80, y), line, fill="black", font=font)
        y += 105
    img.save(path)
    return path


def setUpModule():
    global _ENGINE_READY
    if sys.platform != "win32":
        try:
            import tesserocr  # noqa: F401
            os.environ["TASHIKAMAIL_TESSERACT_CMD"] = _write_shim()
            _ENGINE_READY = True
        except Exception:
            _ENGINE_READY = False
    else:
        _ENGINE_READY = core.ocr_available()


def _need_engine(testcase):
    if not _ENGINE_READY:
        testcase.skipTest("no runnable tesseract engine in this environment")


class TestTesseractResolution(unittest.TestCase):
    def test_env_override_wins(self):
        with tempfile.TemporaryDirectory() as d:
            fake = os.path.join(d, "custom-tesseract")
            open(fake, "w").close()
            bundled = os.path.join(d, "tesseract", "tesseract.exe")
            os.makedirs(os.path.dirname(bundled))
            open(bundled, "w").close()
            found = core.find_tesseract(
                env={"TASHIKAMAIL_TESSERACT_CMD": fake}, frozen=False,
                app_dir=d, which=lambda name: "/usr/bin/tesseract")
            self.assertEqual(found, fake)

    def test_bundled_beats_path(self):
        with tempfile.TemporaryDirectory() as d:
            bundled = os.path.join(d, "tesseract", "tesseract.exe")
            os.makedirs(os.path.dirname(bundled))
            open(bundled, "w").close()
            found = core.find_tesseract(
                env={}, frozen=False, app_dir=d,
                which=lambda name: "/usr/bin/tesseract")
            self.assertEqual(found, bundled)

    def test_path_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            found = core.find_tesseract(
                env={}, frozen=False, app_dir=d,
                which=lambda name: "/usr/bin/tesseract")
            self.assertEqual(found, "/usr/bin/tesseract")

    def test_darwin_candidates_use_homebrew_not_bundled(self):
        # On macOS the bundled copy is a Windows binary: it must not be
        # a candidate. The Homebrew prefixes take its place (Finder-
        # launched apps do not inherit the shell PATH).
        with mock.patch.object(sys, "platform", "darwin"):
            cands = core.tesseract_candidates(env={}, frozen=False,
                                              app_dir="/nonexistent")
        self.assertIn("/opt/homebrew/bin/tesseract", cands)
        self.assertIn("/usr/local/bin/tesseract", cands)
        self.assertFalse(any(c.endswith("tesseract.exe") for c in cands))

    def test_darwin_find_prefers_homebrew(self):
        with mock.patch.object(sys, "platform", "darwin"), \
                mock.patch.object(
                    core.os.path, "isfile",
                    lambda p: p == "/opt/homebrew/bin/tesseract"):
            found = core.find_tesseract(env={}, frozen=False,
                                        app_dir="/nonexistent",
                                        which=lambda name: None)
        self.assertEqual(found, "/opt/homebrew/bin/tesseract")

    def test_darwin_env_override_still_wins(self):
        with tempfile.TemporaryDirectory() as d:
            fake = os.path.join(d, "custom-tesseract")
            open(fake, "w").close()
            bundled = os.path.join(d, "tesseract", "tesseract.exe")
            os.makedirs(os.path.dirname(bundled))
            open(bundled, "w").close()
            with mock.patch.object(sys, "platform", "darwin"):
                found = core.find_tesseract(
                    env={"TASHIKAMAIL_TESSERACT_CMD": fake}, frozen=False,
                    app_dir=d, which=lambda name: None)
            self.assertEqual(found, fake)

    def test_tessdata_discovery_and_lang_string(self):
        with tempfile.TemporaryDirectory() as d:
            td = os.path.join(d, "tesseract", "tessdata")
            os.makedirs(td)
            for code in ("jpn", "eng", "kor"):
                open(os.path.join(td, code + ".traineddata"), "w").close()
            found = core.find_tessdata_dir(env={}, frozen=False, app_dir=d)
            self.assertEqual(found, td)
            self.assertEqual(core.ocr_lang_string("ko", td), "jpn+eng+kor")
            # spa has no data file here, so it is dropped honestly
            self.assertEqual(core.ocr_lang_string("es", td), "jpn+eng")


class TestOcrFunctional(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.en_img = os.path.join(_TMP, "invoice_en.png")
        cls.ja_img = os.path.join(_TMP, "invoice_ja.png")
        if os.path.exists(DEJAVU):
            _make_image(EN_LINES, DEJAVU, cls.en_img)
        if os.path.exists(NOTO):
            _make_image(JA_LINES, NOTO, cls.ja_img)

    def test_image_invoice_extraction_en(self):
        _need_engine(self)
        if not os.path.exists(self.en_img):
            self.skipTest("DejaVu font unavailable")
        att = core.read_attachment(self.en_img)
        self.assertTrue(att.via_ocr)
        self.assertTrue(att.readable)
        totals = [a for a in att.amounts if a.kind == "total"]
        self.assertTrue(any(a.value == Decimal("1100.00")
                            and a.currency == "USD" for a in totals),
                        att.amounts)
        self.assertIn("INV1001", att.doc_numbers)
        self.assertIn("2026-11-14", [str(d.day) for d in att.dates])

    def test_image_pipeline_green_then_red(self):
        _need_engine(self)
        if not os.path.exists(self.en_img):
            self.skipTest("DejaVu font unavailable")
        inp = core_checks.CheckInput(
            recipients_text="taro@alphacorp.co.jp",
            subject="Invoice INV-1001", body=BODY_OK,
            attachments=[core.read_attachment(self.en_img)],
            country="JP")
        report = core_checks.run_checks(inp)
        self.assertEqual(report.overall, "green",
                         [(f.check, f.level, f.reason_key)
                          for f in report.findings])
        readable = [f for f in report.by_check("readable")
                    if f.reason_key == "r_read_via_ocr"]
        self.assertTrue(readable)  # OCR provenance is shown
        caution = report.by_check("ocr")
        self.assertEqual(len(caution), 1)
        self.assertEqual(caution[0].reason_key, "r_ocr_caution")

        inp2 = core_checks.CheckInput(
            recipients_text="taro@alphacorp.co.jp",
            subject="Invoice INV-1001",
            body=BODY_OK.replace("$1,100.00", "$1,200.00"),
            attachments=[core.read_attachment(self.en_img)],
            country="JP")
        report2 = core_checks.run_checks(inp2)
        self.assertEqual(report2.by_check("amount")[0].level, "red")
        self.assertEqual(report2.overall, "red")

    def test_image_invoice_japanese(self):
        _need_engine(self)
        if not os.path.exists(self.ja_img):
            self.skipTest("Noto CJK font unavailable")
        att = core.read_attachment(self.ja_img)
        self.assertTrue(att.via_ocr)
        totals = [a for a in att.amounts if a.kind == "total"]
        self.assertTrue(any(a.value == Decimal("55000")
                            and a.currency == "JPY" for a in totals),
                        att.amounts)
        self.assertIn("INV2001", att.doc_numbers)
        self.assertIn("サクラ", att.companies)
        inp = core_checks.CheckInput(
            recipients_text="", subject="請求書 INV-2001", body=BODY_JA,
            attachments=[att], country="JP")
        report = core_checks.run_checks(inp)
        self.assertEqual(report.by_check("amount")[0].level, "green")
        self.assertEqual(report.by_check("docnum")[0].level, "green")

    def test_scanned_pdf_image_only(self):
        _need_engine(self)
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF unavailable")
        if not os.path.exists(self.en_img):
            self.skipTest("DejaVu font unavailable")
        pdf_path = os.path.join(_TMP, "scan.pdf")
        doc = fitz.open()
        page = doc.new_page(width=595, height=420)
        page.insert_image(page.rect, filename=self.en_img)
        doc.save(pdf_path)
        doc.close()
        att = core.read_attachment(pdf_path)
        self.assertTrue(att.via_ocr)
        self.assertEqual(att.ocr_pages, 1)
        totals = [a for a in att.amounts if a.kind == "total"]
        self.assertTrue(any(a.value == Decimal("1100.00") for a in totals),
                        att.amounts)
        self.assertIn("INV1001", att.doc_numbers)

    def test_mixed_pdf_text_and_scan_pages(self):
        _need_engine(self)
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF unavailable")
        if not os.path.exists(self.en_img):
            self.skipTest("DejaVu font unavailable")
        pdf_path = os.path.join(_TMP, "mixed.pdf")
        doc = fitz.open()
        p1 = doc.new_page(width=595, height=200)
        p1.insert_text((72, 100), "Cover memo: see scanned invoice next page.")
        p2 = doc.new_page(width=595, height=420)
        p2.insert_image(p2.rect, filename=self.en_img)
        doc.save(pdf_path)
        doc.close()
        att = core.read_attachment(pdf_path)
        self.assertIn("Cover memo", att.text)       # text layer kept
        self.assertEqual(att.ocr_pages, 1)          # only page 2 via OCR
        self.assertIn("INV1001", att.doc_numbers)

    def test_blank_image_stays_unreadable(self):
        _need_engine(self)
        from PIL import Image
        blank = os.path.join(_TMP, "blank.png")
        Image.new("RGB", (800, 600), "white").save(blank)
        att = core.read_attachment(blank)
        self.assertFalse(att.readable)
        self.assertFalse(att.via_ocr)
        inp = core_checks.CheckInput(
            recipients_text="", subject="", body="hello",
            attachments=[att], country="JP")
        report = core_checks.run_checks(inp)
        readable = report.by_check("readable")
        self.assertEqual(readable[0].level, "yellow")
        self.assertEqual(readable[0].reason_key, "r_unreadable")
        self.assertEqual(report.by_check("ocr"), [])  # no caution w/o OCR

    def test_eml_image_attachment_ocr(self):
        _need_engine(self)
        if not os.path.exists(self.en_img):
            self.skipTest("DejaVu font unavailable")
        msg = email.message.EmailMessage()
        msg["From"] = "a@example.com"
        msg["To"] = "taro@alphacorp.co.jp"
        msg["Subject"] = "Invoice INV-1001"
        msg.set_content(BODY_OK)
        with open(self.en_img, "rb") as fh:
            msg.add_attachment(fh.read(), maintype="image", subtype="png",
                               filename="invoice_en.png")
        eml_path = os.path.join(_TMP, "mail.eml")
        with open(eml_path, "wb") as fh:
            fh.write(bytes(msg))
        out_dir = os.path.join(_TMP, "eml_parts")
        data = core.parse_eml(eml_path, keep_attachments=True,
                              out_dir=out_dir)
        self.assertEqual(len(data["attachments"]), 1)
        att = core.read_attachment(data["attachments"][0]["path"],
                                   data["attachments"][0]["name"])
        self.assertTrue(att.via_ocr)
        self.assertIn("INV1001", att.doc_numbers)


if __name__ == "__main__":
    unittest.main()

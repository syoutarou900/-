# -*- coding: utf-8 -*-
"""Tests for TashikaMail core logic. Runnable with pytest or unittest."""
import datetime
import email
import email.policy
import os
import sys
import tempfile
import unittest
from email.message import EmailMessage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import core
import core_checks as cc


def make_pdf(path, lines):
    """Minimal single-page PDF with a text layer (uncompressed stream)."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    ops = ["BT", "/F1 12 Tf", "50 780 Td"]
    for i, line in enumerate(lines):
        if i:
            ops.append("0 -16 Td")
        ops.append(f"({esc(line)}) Tj")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF").encode()
    with open(path, "wb") as fh:
        fh.write(bytes(out))


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


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tashikamail_test_")

    def write_att(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return core.read_attachment(path)

    def check(self, **kw):
        defaults = dict(
            recipients_text="taro@alphacorp.co.jp", subject="Invoice INV-1001",
            body=BODY_OK, attachments=[self.write_att("invoice.txt", ATT_OK)],
            country="JP")
        defaults.update(kw)
        return cc.run_checks(cc.CheckInput(**defaults))

    def finding(self, report, check):
        items = report.by_check(check)
        self.assertTrue(items, f"no finding for {check}")
        return items[0]


class TestGreen(Base):
    def test_green_all_ok(self):
        report = self.check()
        self.assertEqual(report.overall, "green",
                         [(f.check, f.level, f.reason_key)
                          for f in report.findings])


class TestRedCases(Base):
    def test_amount_mismatch_red(self):
        att = self.write_att("invoice.txt",
                             ATT_OK.replace("$1,100.00", "$1,200.00"))
        report = self.check(attachments=[att])
        self.assertEqual(self.finding(report, "amount").level, "red")
        self.assertEqual(report.overall, "red")

    def test_missing_attachment_red(self):
        report = self.check(attachments=[])
        self.assertEqual(self.finding(report, "attach").level, "red")
        self.assertEqual(report.overall, "red")

    def test_docnum_mismatch_red(self):
        att = self.write_att("invoice.txt",
                             ATT_OK.replace("INV-1001", "INV-1002"))
        report = self.check(attachments=[att])
        self.assertEqual(self.finding(report, "docnum").level, "red")

    def test_deadline_mismatch_red(self):
        att = self.write_att("invoice.txt",
                             ATT_OK.replace("2026/11/30", "2026/12/01"))
        report = self.check(attachments=[att])
        f = self.finding(report, "date")
        self.assertEqual(f.level, "red")
        self.assertEqual(f.reason_key, "r_date_deadline_mismatch")

    def test_expected_domain_mismatch_red(self):
        report = self.check(expected_domain="alphacorp.co.jp",
                            recipients_text="taro@othercorp.com")
        self.assertEqual(self.finding(report, "domain").level, "red")

    def test_duplicate_versions_red(self):
        a1 = self.write_att("invoice_v1.txt", ATT_OK)
        a2 = self.write_att("invoice_v2.txt", ATT_OK)
        report = self.check(attachments=[a1, a2])
        dups = [f for f in report.by_check("version")
                if f.reason_key == "r_version_duplicate"]
        self.assertTrue(dups)
        self.assertEqual(dups[0].level, "red")


class TestYellowCases(Base):
    def test_domain_mismatch_yellow(self):
        report = self.check(recipients_text="taro@othercorp.com")
        self.assertEqual(self.finding(report, "domain").level, "yellow")

    def test_freemail_yellow(self):
        report = self.check(recipients_text="taro@gmail.com")
        f = self.finding(report, "domain")
        self.assertEqual(f.level, "yellow")
        self.assertEqual(f.reason_key, "r_domain_freemail")

    def test_old_filename_date(self):
        att = self.write_att("invoice_20260101.txt", ATT_OK)
        report = self.check(attachments=[att])
        vf = [f for f in report.by_check("version")
              if f.reason_key == "r_version_filename_old"]
        self.assertTrue(vf)
        self.assertIn(vf[0].level, ("yellow", "red"))
        self.assertNotEqual(report.overall, "green")

    def test_japanese_filename_us_yellow_and_rename(self):
        text = ("請求書\n請求番号 INV-1001\n日付 2026/11/14\n"
                "合計 ¥110,000\n株式会社アルファ")
        body = ("株式会社アルファ 御中\n請求書を添付いたします。\n"
                "請求番号: INV-1001\n発行日: 2026/11/14\n合計金額: ¥110,000")
        att = self.write_att("請求書_20261114.txt", text)
        report = self.check(body=body, attachments=[att], country="US",
                            recipients_text="taro@alpha.co.jp",
                            subject="請求書")
        jf = [f for f in report.by_check("filename")
              if f.reason_key == "r_filename_japanese"]
        self.assertTrue(jf)
        self.assertEqual(jf[0].level, "yellow")
        self.assertIn(att.path, report.rename_suggestions)
        suggestion = report.rename_suggestions[att.path]
        suggestion.encode("ascii")  # must be ASCII-safe
        self.assertTrue(suggestion.endswith(".txt"))

    def test_unreadable_attachment_yellow(self):
        path = os.path.join(self.tmp, "scan.png")
        with open(path, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n" + bytes(range(256)))
        att = core.read_attachment(path)
        report = self.check(attachments=[att])
        f = self.finding(report, "readable")
        self.assertEqual(f.level, "yellow")
        self.assertNotEqual(report.overall, "green")

    def test_no_recipient_red(self):
        report = self.check(recipients_text="")
        self.assertEqual(self.finding(report, "domain").level, "red")


class TestNormalization(Base):
    def test_company_legal_form_variants(self):
        body = "株式会社サクラ 御中\n請求書を添付いたします。"
        att = self.write_att("inv.txt", "請求書\n（株）サクラ\n合計 ¥10,000")
        report = self.check(body=body, attachments=[att],
                            recipients_text="a@sakura.co.jp")
        self.assertEqual(self.finding(report, "company").level, "green")

    def test_company_mismatch_red(self):
        body = "株式会社サクラ 御中\n請求書を添付いたします。"
        att = self.write_att("inv.txt", "請求書\n株式会社ウメ\n合計 ¥10,000")
        report = self.check(body=body, attachments=[att],
                            recipients_text="a@sakura.co.jp")
        self.assertEqual(self.finding(report, "company").level, "red")

    def test_wareki_and_english_dates(self):
        hits = core.extract_dates("令和8年11月14日")
        self.assertEqual([h.day for h in hits],
                         [datetime.date(2026, 11, 14)])
        hits = core.extract_dates("Nov 14, 2026 / 14 Nov 2026")
        self.assertEqual({h.day for h in hits},
                         {datetime.date(2026, 11, 14)})

    def test_fullwidth_amount(self):
        amounts = core.extract_amounts("合計金額：￥１１０，０００（税込）")
        self.assertEqual(len(amounts), 1)
        self.assertEqual(amounts[0].value, 110000)
        self.assertEqual(amounts[0].kind, "total")


class TestReaders(Base):
    def test_pdf_reader(self):
        path = os.path.join(self.tmp, "invoice.pdf")
        make_pdf(path, ["Invoice No. INV-2001", "Total $500.00",
                        "Alphacorp Inc."])
        att = core.read_attachment(path)
        self.assertTrue(att.readable, att.error)
        self.assertIn("INV-2001", att.text)
        totals = [a for a in att.amounts if a.kind == "total"]
        self.assertTrue(totals and totals[0].value == 500)

    def test_xlsx_reader(self):
        import openpyxl
        path = os.path.join(self.tmp, "invoice.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws["A1"] = "Invoice No. INV-3001"
        ws["A2"] = "Total"
        ws["B2"] = "$700.00"
        wb.save(path)
        att = core.read_attachment(path)
        self.assertTrue(att.readable, att.error)
        self.assertIn("INV-3001", att.text)

    def test_docx_reader(self):
        import docx
        path = os.path.join(self.tmp, "invoice.docx")
        doc = docx.Document()
        doc.add_paragraph("Invoice No. INV-4001 Total $900.00")
        doc.save(path)
        att = core.read_attachment(path)
        self.assertTrue(att.readable, att.error)
        self.assertIn("INV-4001", att.text)


class TestEml(Base):
    def test_eml_decomposition(self):
        msg = EmailMessage()
        msg["From"] = "me@mycompany.example"
        msg["To"] = "taro@alphacorp.co.jp"
        msg["Subject"] = "Invoice INV-1001"
        msg.set_content(BODY_OK)
        msg.add_attachment(ATT_OK.encode("utf-8"),
                           maintype="text", subtype="plain",
                           filename="invoice.txt")
        path = os.path.join(self.tmp, "mail.eml")
        with open(path, "wb") as fh:
            fh.write(bytes(msg))
        data = core.parse_eml(path, out_dir=os.path.join(self.tmp, "parts"))
        self.assertIn("taro@alphacorp.co.jp", data["recipients"][0])
        self.assertEqual(data["subject"], "Invoice INV-1001")
        self.assertIn("INV-1001", data["body"])
        self.assertEqual(len(data["attachments"]), 1)
        att = core.read_attachment(data["attachments"][0]["path"],
                                   data["attachments"][0]["name"])
        self.assertTrue(att.readable)
        self.assertIn("INV-1001", att.text)


class TestExpected(Base):
    def test_expected_amount_ok(self):
        report = self.check(expected_amount="$1,100.00")
        self.assertEqual(self.finding(report, "amount").level, "green")

    def test_expected_amount_mismatch_red(self):
        report = self.check(expected_amount="$9,999.00")
        f = self.finding(report, "amount")
        self.assertEqual(f.level, "red")
        self.assertEqual(f.reason_key, "r_amount_expected_mismatch")


class TestI18nAndSafety(unittest.TestCase):
    def test_i18n_key_parity(self):
        import i18n
        base = set(i18n.JA)
        self.assertEqual(len(i18n.STRINGS), 13)
        for code, table in i18n.STRINGS.items():
            self.assertEqual(set(table), base, f"key mismatch in {code}")

    def test_no_send_capability_in_source(self):
        here = os.path.join(os.path.dirname(__file__), "..")
        for name in ("app.py", "core.py", "core_checks.py"):
            with open(os.path.join(here, name), encoding="utf-8") as fh:
                src = fh.read().lower()
            self.assertNotIn("smtplib", src, name)
            self.assertNotIn("sendmail", src, name)

    def test_no_fuzzy_library(self):
        here = os.path.join(os.path.dirname(__file__), "..")
        for name in ("core.py", "core_checks.py"):
            with open(os.path.join(here, name), encoding="utf-8") as fh:
                src = fh.read().lower()
            self.assertNotIn("difflib", src, name)
            self.assertNotIn("fuzzy", src.replace("no fuzzy", ""), name)


if __name__ == "__main__":
    unittest.main()

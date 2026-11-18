# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core


# ------------------------------------------------------------ normalization
def test_normalize_fullwidth_digits_and_space():
    assert core.normalize("１２，３４５") == "12,345" or core.normalize("１２３４５") == "12345"
    assert core.normalize("　ＡＢＣ　") == "abc"
    assert core.normalize("  Hello   World ") == "hello world"


def test_parse_number_separators_and_yen():
    assert core.parse_number("12,000") == core.parse_number("12000")
    assert core.parse_number("１２，０００円") == 12000
    assert core.parse_number("abc") is None
    assert core.parse_number("") is None


def test_compare_match_fullwidth_and_separator():
    assert core.compare("12,000", "１２０００")["status"] == "match"
    assert core.compare("サンプル商事", "サンプル商事")["status"] == "match"
    assert core.compare("ABC-001", "abc-001")["status"] == "match"


def test_compare_empty_and_mismatch_text():
    assert core.compare("10", "")["status"] == "empty"
    assert core.compare("10", "   ")["status"] == "empty"
    r = core.compare("サンプル商事", "サンプル商会")
    assert r["status"] == "mismatch" and r["reason"] == "text" and r["diff_pos"] == 6


def test_compare_digit_reason():
    r = core.compare("12000", "1200")
    assert r["status"] == "mismatch" and r["reason"] == "digits"
    assert r["src_digits"] == 5 and r["in_digits"] == 4
    r2 = core.compare("12000", "12001")
    assert r2["status"] == "mismatch" and r2["reason"] == "number"


def test_digit_count():
    assert core.digit_count("1,234") == 4
    assert core.digit_count("１２３") == 3
    assert core.digit_count("abc") is None


# ------------------------------------------------------------ stats/totals
def test_compute_stats():
    items = core.sample_items()
    inputs = [""] * len(items)
    s = core.compute_stats(items, inputs)
    assert s == {"total": len(items), "done": 0, "remaining": len(items), "mismatch": 0}
    inputs = [it["value"] for it in items]
    s = core.compute_stats(items, inputs)
    assert s["done"] == len(items) and s["remaining"] == 0 and s["mismatch"] == 0
    inputs[2] = "999"  # 数量 of first line (10) -> mismatch
    s = core.compute_stats(items, inputs)
    assert s["mismatch"] == 1 and s["remaining"] == 0


def test_field_totals():
    items = [
        {"group": "a", "field": "金額", "value": "100"},
        {"group": "b", "field": "金額", "value": "250"},
        {"group": "a", "field": "数量", "value": "2"},
    ]
    totals = {t["field"]: t for t in core.field_totals(items, ["100", "200", "2"])}
    assert totals["金額"]["source_sum"] == 350
    assert totals["金額"]["typed_sum"] == 300
    assert totals["金額"]["match"] is False
    assert totals["数量"]["match"] is True
    totals2 = {t["field"]: t for t in core.field_totals(items, ["100", "250", "2"])}
    assert totals2["金額"]["match"] is True


# ------------------------------------------------------------ extractors
def test_extract_csv_text():
    text = "品名,数量,単価\nりんご,10,150\nバナナ,5,80\n"
    items = core.extract_text(text)
    fields = {(i["group"], i["field"], i["value"]) for i in items}
    assert ("りんご", "数量", "10") in fields
    assert ("バナナ", "単価", "80") in fields
    assert ("りんご", "品名", "りんご") in fields  # nothing dropped


def test_extract_txt_keyvalue_and_lines():
    items = core.extract_text("請求番号: INV-001\n取引先：テスト商事\nただの行\n")
    kv = {(i["field"], i["value"]) for i in items}
    assert ("請求番号", "INV-001") in kv
    assert ("取引先", "テスト商事") in kv
    assert any(i["value"] == "ただの行" for i in items)


def test_extract_tab_table():
    items = core.extract_text("品名\t数量\nペン\t30\n")
    assert any(i["field"] == "数量" and i["value"] == "30" and i["group"] == "ペン" for i in items)


def test_extract_xlsx(tmp_path):
    from openpyxl import Workbook
    path = tmp_path / "src.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["品名", "数量", "金額"])
    ws.append(["ノート", 3, 450])
    ws.append(["ペン", 10, 1000])
    wb.save(path)
    items = core.extract_xlsx(str(path))
    assert any(i["group"] == "ノート" and i["field"] == "金額" and i["value"] == "450" for i in items)
    assert any(i["group"] == "ペン" and i["field"] == "数量" and i["value"] == "10" for i in items)


def test_extract_pdf_fixture(tmp_path):
    import fitz
    path = tmp_path / "src.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "請求番号: INV-2026-001", fontsize=11, fontname="japan")
    page.insert_text((72, 96), "取引先: サンプル商事", fontsize=11, fontname="japan")
    doc.save(path)
    doc.close()
    items = core.extract_pdf(str(path))
    kv = {(i["field"], i["value"]) for i in items}
    assert ("請求番号", "INV-2026-001") in kv
    assert ("取引先", "サンプル商事") in kv


def test_extract_csv_bytes_sjis():
    text = "品名,数量\n鉛筆,12\n"
    items = core.extract_csv(text.encode("cp932"))
    assert any(i["value"] == "12" and i["group"] == "鉛筆" for i in items)


# ------------------------------------------------------------ sample/session
def test_sample_integrity():
    items = core.sample_items()
    by_group = {}
    for i in items:
        by_group.setdefault(i["group"], {})[i["field"]] = i["value"]
    total = 0
    for name, fields in by_group.items():
        if "数量" in fields and "単価" in fields and "金額" in fields:
            assert int(fields["数量"]) * int(fields["単価"]) == int(fields["金額"])
            total += int(fields["金額"])
    assert int(by_group["合計"]["合計"]) == total


def test_build_tsv_and_session_roundtrip():
    items = core.sample_items()[:3]
    inputs = ["x", "y", "z"]
    tsv = core.build_tsv(items, inputs)
    lines = tsv.strip().split("\r\n")
    assert lines[0] == "group\tfield\tvalue" and len(lines) == 4
    d = core.session_dict(items, inputs, "en", "f.xlsx")
    items2, inputs2, lang, name = core.session_from_dict(d)
    assert items2 == items and inputs2 == inputs and lang == "en" and name == "f.xlsx"


def test_ocr_notice_when_unavailable(monkeypatch):
    # On machines without tesseract this returns the notice; with tesseract
    # the image path is exercised separately. Here we only assert the API.
    items, notice = core.extract_image(__file__)  # not an image; must not fake results
    assert isinstance(items, list)
    if not core.ocr_available():
        assert notice == "ocr_unavailable" and items == []

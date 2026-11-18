# -*- coding: utf-8 -*-
import os
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import core
from core import Table

FIX = os.path.join(os.path.dirname(__file__), "fixture_mufg.js")


def tbl(headers, rows):
    return Table(headers, rows)


# --------------------------------------------------------------- dates
def test_date_ambiguous_flagged():
    t = tbl(["日付", "品名"], [["03/04", "A"], ["05/06", "B"]])
    r = core.convert_table(t, "GB", "JP")
    assert r.report["unresolved"] == 2
    assert {x.kind for x in r.reviews} == {"date"}
    # unresolved cells keep original text
    assert r.rows[0][0] == "03/04"


def test_date_column_evidence_proves_dmy():
    t = tbl(["日付"], [["25/03"], ["03/04"]])
    r = core.convert_table(t, "GB", "JP")
    assert r.report["unresolved"] == 0
    # yearless input -> yearless output in receiver (JP: month/day) order
    assert r.rows[0][0] == "03/25"  # 25/03 DMY = 25 Mar
    assert r.rows[1][0] == "04/03"  # 03/04 DMY = 3 Apr


def test_date_us_to_jp_with_evidence():
    t = tbl(["Date"], [["12/25/2026"], ["03/04/2026"]])
    r = core.convert_table(t, "US", "JP")
    assert r.report["unresolved"] == 0
    assert r.rows[0][0] == "2026/12/25"
    assert r.rows[1][0] == "2026/03/04"


def test_date_resolution_applies():
    t = tbl(["日付"], [["03/04"]])
    r0 = core.convert_table(t, "GB", "JP")
    assert r0.report["unresolved"] == 1
    pk = r0.reviews[0].pattern_key
    cand = r0.reviews[0].candidates[0]  # DMY -> 2026-04-03
    r = core.convert_table(t, "GB", "JP", resolutions={pk: cand["output"]})
    assert r.report["unresolved"] == 0
    assert r.rows[0][0] == cand["output"]


# --------------------------------------------------------------- numbers
def test_eu_number_to_plain_and_us():
    v, info = core.parse_number("1.234,56", ",", ".")
    assert v == Decimal("1234.56") and not info["ambiguous"]
    t = tbl(["金額"], [["1.234,56"]])
    r = core.convert_table(t, "DE", "JP")
    assert r.rows[0][0] == "1,234.56"
    r2 = core.convert_table(t, "DE", "US")
    assert r2.rows[0][0] == "1,234.56"


def test_number_ambiguous_flagged():
    t = tbl(["金額"], [["1.234"]])
    r = core.convert_table(t, "DE", "US")
    assert r.report["unresolved"] == 1
    item = r.reviews[0]
    assert item.kind == "number"
    outs = {c["output"] for c in item.candidates}
    assert outs == {"1,234", "1.234"}


def test_number_column_evidence_resolves():
    t = tbl(["金額"], [["1.234.567,89"], ["1.234"]])
    r = core.convert_table(t, "DE", "US")
    assert r.report["unresolved"] == 0
    assert r.rows[1][0] == "1,234"


def test_fullwidth_digits():
    assert core.normalize_fullwidth("１２３") == "123"
    t = tbl(["金額"], [["１２３４５"]])
    r = core.convert_table(t, "JP", "US")
    assert r.rows[0][0] == "12,345"
    # dotted fullwidth amount with a decimal tail converts too
    t2 = tbl(["金額"], [["１，２３４．５６"]])
    r2 = core.convert_table(t2, "JP", "US")
    assert r2.rows[0][0] == "1,234.56"


def test_leading_zero_code_preserved():
    t = tbl(["商品コード", "品名"], [["007", "A"], ["012", "B"]])
    r = core.convert_table(t, "JP", "US")
    assert r.rows[0][0] == "007"
    assert r.rows[1][0] == "012"
    assert r.report["counts"]["preserved_code"] >= 2


# --------------------------------------------------------------- wareki
def test_wareki_to_gregorian():
    assert core.wareki_to_date("令和8年11月13日") == date(2026, 11, 13)
    assert core.wareki_to_date("令和元年5月1日") == date(2019, 5, 1)
    assert core.wareki_to_date("R8.11.13") == date(2026, 11, 13)
    assert core.wareki_to_date("平成31年4月30日") == date(2019, 4, 30)


def test_gregorian_to_wareki():
    assert core.date_to_wareki(date(2026, 11, 13)) == "令和8年11月13日"
    assert core.date_to_wareki(date(2019, 5, 1)) == "令和元年5月1日"
    assert core.date_to_wareki(date(1989, 1, 8)) == "平成元年1月8日"


def test_wareki_column_converts():
    t = tbl(["日付"], [["令和8年11月13日"]])
    r = core.convert_table(t, "JP", "US")
    assert r.rows[0][0] == "11/13/2026"
    assert r.report["counts"]["wareki"] == 1


# --------------------------------------------------------------- csv io
def test_semicolon_csv_loads_columns(tmp_path):
    p = tmp_path / "eu.csv"
    p.write_bytes("Datum;Betrag\n25.03.2026;1.234,56\n".encode("utf-8"))
    t = core.load_table(str(p))
    assert t.headers == ["Datum", "Betrag"]
    assert t.rows[0][1] == "1.234,56"
    assert t.meta["delimiter"] == ";"


def test_shift_jis_csv_decodes(tmp_path):
    p = tmp_path / "jp.csv"
    p.write_bytes("品名,金額\nりんご,100\n".encode("shift_jis"))
    t = core.load_table(str(p))
    assert t.headers[0] == "品名"
    assert t.rows[0][0] == "りんご"
    assert t.meta["encoding"] == "shift_jis"


def test_csv_roundtrip_delimiter():
    t = tbl(["a", "b"], [["1", "2"]])
    data = core.table_to_csv_text(t, delimiter=";")
    t2, d = core.parse_csv_text(data.decode("utf-8-sig"), ";")
    assert t2.rows == [["1", "2"]]


# --------------------------------------------------------------- fx math
FR = {"source": "frankfurter", "base": "USD", "date": "2026-11-12",
      "rates": {"USD": Decimal(1), "JPY": Decimal("160"), "EUR": Decimal("0.9")}}


def test_fx_ref_cross_rate_and_rounding():
    out, rate, label = core.fx_convert(Decimal("100"), "EUR", "JPY", "ref", {"bundle": FR})
    # 100 EUR -> USD 111.11 -> JPY 17777.78 -> minor 0 -> 17778
    assert out == Decimal("17778")
    assert "ECB基準レート" in label and "2026-11-12" in label


def test_fx_ref_minor_units_3():
    bundle = {"source": "erapi", "base": "USD", "date": "x",
              "rates": {"USD": Decimal(1), "BHD": Decimal("0.376")}}
    out, rate, label = core.fx_convert(Decimal("100"), "USD", "BHD", "ref", {"bundle": bundle})
    assert out == Decimal("37.600")
    assert "公式基準レートではありません" in label


def test_fx_bank_direction_tts_ttb():
    mufg = {"source": "mufg", "date": "2026年11月13日 21時40分",
            "pairs": {"USD": (Decimal("160.26"), Decimal("159.76"))}}
    # foreign -> JPY uses TTB
    out, rate, label = core.fx_convert(Decimal("100"), "USD", "JPY", "bank", {"mufg": mufg})
    assert out == Decimal("15976")
    assert "TTB" in rate and "三菱UFJ" in label
    # JPY -> foreign uses TTS
    out2, rate2, _ = core.fx_convert(Decimal("16026"), "JPY", "USD", "bank", {"mufg": mufg})
    assert out2 == Decimal("100.00")
    assert "TTS" in rate2


def test_fx_bank_unavailable_pair():
    mufg = {"source": "mufg", "date": "x", "pairs": {"USD": (Decimal("1"), Decimal("1"))}}
    out, reason, _ = core.fx_convert(Decimal("10"), "EUR", "JPY", "bank", {"mufg": mufg})
    assert out is None and "not available" in reason


def test_fx_manual_single_rate():
    out, rate, label = core.fx_convert(
        Decimal("50"), "USD", "EUR", "manual",
        {"bank_name": "テスト銀行", "rate": "0.9"})
    assert out == Decimal("45.00") and "テスト銀行" in label


def test_mufg_parser_against_real_fixture():
    with open(FIX, "rb") as fh:
        parsed = core.parse_mufg_js(fh.read())
    assert parsed is not None
    assert parsed["date"].startswith("2026年11月13日")
    assert set(parsed["pairs"]) == {"USD", "EUR", "GBP", "CHF", "AUD",
                                    "NZD", "ZAR", "TRY", "CNY"}
    tts, ttb = parsed["pairs"]["USD"]
    assert tts > ttb > 0


def test_mufg_parser_garbage_returns_none():
    assert core.parse_mufg_js("var x = {\"foo\": 1}") is None


def test_fx_cache_roundtrip(tmp_path):
    core.save_fx_cache({"frankfurter": FR}, directory=str(tmp_path))
    loaded = core.load_fx_cache(directory=str(tmp_path))
    assert loaded["frankfurter"]["rates"]["JPY"] == Decimal("160")


def test_convert_with_fx_ref():
    t = tbl(["金額"], [["100,00"]])
    r = core.convert_table(t, "DE", "JP", fx={"mode": "ref", "ctx": {"bundle": FR}})
    # 100 EUR -> JPY 17778 (rate table above), formatted JP, minor 0
    assert r.rows[0][0] == "17,778"
    assert r.report["fx_label"].startswith("ECB基準レート")
    assert r.report["counts"]["fx"] == 1


def test_same_currency_no_fx_change():
    t = tbl(["金額"], [["1.234,56"]])
    r = core.convert_table(t, "DE", "FR", fx={"mode": "ref", "ctx": {"bundle": FR}})
    assert r.rows[0][0] == "1 234,56" or r.rows[0][0] == "1234,56"

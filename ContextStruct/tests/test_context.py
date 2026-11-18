# -*- coding: utf-8 -*-
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from context_core import *
from i18n_data import TRANSLATIONS, LANG_ORDER

DELIVERY = """納品書
納品書番号: DN-2026-001
納品日: 2026年11月12日
取引先: 株式会社サンプル
商品名: りんごジュース 1L
数量: 24
卸値: 800円
売価: 1200円
合計: 19200円
"""
INVOICE = """請求書
請求書番号: INV-2026-042
請求日: 2026/11/01
請求先: 株式会社テスト
小計: 50000円
消費税: 5000円
請求金額: 55000円
"""

def _profile(name_part):
    for p in preset_profiles():
        if name_part in p.name: return p
    raise AssertionError(name_part)

def test_delivery_wholesale_vs_retail():
    prof=_profile("納品書")
    rows=extract_document(DELIVERY, prof)
    d=rows_to_dicts(rows, prof)[0]
    assert d["卸値"]=="800", d
    assert d["売価"]=="1200", d
    assert d["卸値"]!=d["売価"]
    assert d["納品書番号"]=="DN-2026-001"
    assert d["数量"]=="24"

def test_invoice_extract():
    prof=_profile("請求書")
    rows=extract_document(INVOICE, prof)
    d=rows_to_dicts(rows, prof)[0]
    assert d["請求書番号"]=="INV-2026-042", d
    assert d["請求日"]=="2026-11-01", d
    assert d["請求金額"]=="55000", d

def test_parse_date_cases():
    assert parse_date("2026/11/12")=="2026-11-12"
    assert parse_date("2026-11-12")=="2026-11-12"
    assert parse_date("2026年11月12日")=="2026-11-12"
    assert parse_date("12 Nov 2026")=="2026-11-12"
    assert parse_date("Nov 12, 2026")=="2026-11-12"

def test_parse_number_cases():
    assert parse_number("¥1,200円")=="1200"
    assert parse_number("$1,234.50")=="1234.5"
    assert parse_number("€ 800")=="800"
    assert parse_number("1,9200")=="19200" or parse_number("19,200")=="19200"
    assert parse_number("19,200円")=="19200"

def test_confidence_category():
    assert confidence_category(100)=="green"
    assert confidence_category(80)=="green"
    assert confidence_category(79)=="yellow"
    assert confidence_category(50)=="yellow"
    assert confidence_category(49)=="red"
    assert confidence_category(0)=="red"

def test_tsv_order():
    prof=_profile("納品書")
    rows=extract_document(DELIVERY, prof)
    tsv=rows_to_tsv(rows, prof, include_header=True)
    header=tsv.splitlines()[0].split("\t")
    assert header==[f.target_column for f in prof.fields]
    # wholesale column appears before retail and values in correct columns
    vals=tsv.splitlines()[1].split("\t")
    assert vals[header.index("卸値")]=="800"
    assert vals[header.index("売価")]=="1200"

def test_profile_roundtrip(tmp_path):
    prof=_profile("WEBカタログ")
    path=str(tmp_path/"p.json")
    save_profile(prof, path)
    loaded=load_profile(path)
    assert loaded.name==prof.name
    assert loaded.to_dict()==prof.to_dict()
    # catalog also has separate wholesale/retail
    names=[f.target_column for f in loaded.fields]
    assert "卸値" in names and "売価" in names

def test_i18n_completeness():
    assert LANG_ORDER==["ja","en","es","zh_CN","fr","de","pt","ru","it","tr","ar","id","ko"]
    all_keys=set()
    for lang in LANG_ORDER: all_keys.update(TRANSLATIONS[lang].keys())
    for lang in LANG_ORDER:
        for k in all_keys:
            assert k in TRANSLATIONS[lang], f"{lang} missing {k}"
            assert TRANSLATIONS[lang][k].strip()!="", f"{lang} empty {k}"

def test_pdf_text_extraction(tmp_path):
    import fitz
    p=str(tmp_path/"sample.pdf")
    doc=fitz.open(); page=doc.new_page(); page.insert_text((72,72),"Invoice No: INV-TEST-001 Total 12345"); doc.save(p); doc.close()
    text, ocr = extract_text_from_pdf(p)
    assert "INV-TEST-001" in text
    assert "12345" in text

def test_line_items():
    prof=_profile("納品書")
    text="納品書\n納品日: 2026/11/12\n取引先: 株式会社X\nりんご 10 500\nみかん 20 300\n"
    rows=extract_document(text, prof)
    assert len(rows)>=2
    dicts=rows_to_dicts(rows, prof)
    assert dicts[0]["商品名"]=="りんご"
    assert dicts[1]["商品名"]=="みかん"

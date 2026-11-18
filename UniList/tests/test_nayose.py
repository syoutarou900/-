# -*- coding: utf-8 -*-
"""Tests for UniList core + GUI smoke.

Key guarantees under test:
- candidates are EXACT matches after deterministic normalization
  (no fuzzy/similarity matching anywhere, enforced by a source scan)
- tier A/B/C judgement is deterministic
- only approved groups merge; merges can be undone exactly
- export row-count invariant holds
- 'not a duplicate' learning persists across reloads and sessions
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import core
import normalize as nz


def make_engine(rows, headers=("名前", "住所", "電話", "メール", "ID")):
    eng = core.Engine()
    eng.load(core.Table(list(headers), [list(r) for r in rows]))
    return eng


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def test_name_jp_legal_forms():
    assert nz.normalize_name("株式会社サクラ") == nz.normalize_name("(株)さくら")
    assert nz.normalize_name("有限会社タナカ") == nz.normalize_name("タナカ（有）")
    assert nz.normalize_name("合同会社ABC") == nz.normalize_name("abc")


def test_name_western_legal_forms():
    assert nz.normalize_name("Alphacorp Inc.") == nz.normalize_name("ALPHACORP")
    assert nz.normalize_name("Beta GmbH") == nz.normalize_name("beta")
    assert nz.normalize_name("Acme B.V.") == nz.normalize_name("acme")
    assert nz.normalize_name("Acme Pte. Ltd.") == nz.normalize_name("ACME")
    assert nz.normalize_name("Delta S.A. de C.V.") == nz.normalize_name("delta")


def test_name_accent_folding():
    assert nz.normalize_name("Müller GmbH") == nz.normalize_name("MULLER")
    assert nz.normalize_name("Café René SARL") == nz.normalize_name("cafe rene")


def test_name_kana_folding():
    assert nz.normalize_name("さくら") == nz.normalize_name("サクラ")
    assert nz.normalize_name("じゃぱん") == nz.normalize_name("ジャパン")
    assert nz.normalize_name("ｻｸﾗ") == nz.normalize_name("サクラ")


def test_name_width_and_case():
    assert nz.normalize_name("ＡＢＣ商事") == nz.normalize_name("abc商事")


def test_phone_normalization():
    assert nz.phone_keys("03-1234-5678") == nz.phone_keys("0312345678")
    # international vs domestic trunk
    assert nz.phone_keys("+81 90-1234-5678") & nz.phone_keys("090-1234-5678")
    assert nz.phone_keys("0081-90-1234-5678") & nz.phone_keys("090-1234-5678")
    # different numbers must not match
    assert not (nz.phone_keys("03-1234-5678") & nz.phone_keys("03-1234-5679"))


def test_email_normalization():
    assert nz.normalize_email(" Foo@Example.COM ") == "foo@example.com"
    assert nz.normalize_email("ｆｏｏ@example.com") == "foo@example.com"


def test_address_normalization():
    assert nz.normalize_address("東京都港区1-2-3") == \
        nz.normalize_address("東京都 港区 １－２－３")
    assert nz.normalize_address("Hauptstraße 5") == \
        nz.normalize_address("Hauptstrasse 5")


def test_id_normalization():
    assert nz.normalize_id("T1-2345-6789") == nz.normalize_id("t123456789")


# ---------------------------------------------------------------------------
# Column roles
# ---------------------------------------------------------------------------

def test_role_inference_and_typed_resolution():
    eng = make_engine([["x", "y", "z", "w", "v"]],
                      headers=("会社名", "住所", "電話番号", "メールアドレス", "顧客番号"))
    assert eng.roles == ["name", "address", "phone", "email", "id"]
    # typed corrections tolerate width / case / spaces / synonyms
    assert core.resolve_role("ＮＡＭＥ") == "name"
    assert core.resolve_role("会社 名") == "name"
    assert core.resolve_role("Telephone") == "phone"
    assert core.resolve_role("でんわ") is None  # not a synonym: unresolved
    assert core.resolve_role("住所") == "address"
    assert core.resolve_role("???") is None


# ---------------------------------------------------------------------------
# Candidate detection / tiers
# ---------------------------------------------------------------------------

def test_tier_a_name_and_phone():
    eng = make_engine([
        ["株式会社サクラ", "東京", "03-1234-5678", "a@sakura.jp", ""],
        ["(株)さくら", "大阪", "0312345678", "b@sakura.jp", ""],
    ])
    groups = eng.detect()
    assert len(groups) == 1
    assert groups[0].tier == "A"
    assert "name" in groups[0].reasons and "phone" in groups[0].reasons


def test_tier_b_name_only():
    eng = make_engine([
        ["株式会社サクラ", "東京", "03-1111-1111", "a@x.jp", ""],
        ["サクラ", "大阪", "06-2222-2222", "b@y.jp", ""],
    ])
    groups = eng.detect()
    assert len(groups) == 1 and groups[0].tier == "B"


def test_tier_c_contact_same_name_different():
    eng = make_engine([
        ["サクラ商事", "東京", "03-1234-5678", "", ""],
        ["サクラ物産", "大阪", "03-1234-5678", "", ""],
    ])
    groups = eng.detect()
    assert len(groups) == 1 and groups[0].tier == "C"
    assert "phone" in groups[0].reasons


def test_three_member_group():
    eng = make_engine([
        ["株式会社サクラ", "東京", "03-1234-5678", "", ""],
        ["サクラ", "大阪", "06-9999-9999", "", ""],
        ["(株)サクラ", "名古屋", "052-888-8888", "c@sakura.jp", ""],
    ])
    groups = eng.detect()
    assert len(groups) == 1 and len(groups[0].row_indices) == 3


def test_similar_but_not_equal_names_do_not_match():
    eng = make_engine([
        ["サクラ商事", "東京", "03-1111-1111", "a@x.jp", ""],
        ["サクラ商会", "大阪", "06-2222-2222", "b@y.jp", ""],
        ["サクラ商事2", "名古屋", "052-333-3333", "c@z.jp", ""],
    ])
    assert eng.detect() == []


def test_detection_performance_50k_rows():
    rows = []
    for i in range(25000):
        rows.append([f"会社{i}", "東京", f"03-{i:04d}-0000", f"u{i}@x.jp", ""])
        rows.append([f"会社{i}", "大阪", f"06-{i:04d}-0000", f"v{i}@y.jp", ""])
    eng = make_engine(rows)
    start = time.time()
    groups = eng.detect()
    elapsed = time.time() - start
    assert len(groups) == 25000
    assert elapsed < 20.0  # dict-based grouping; typically ~2-4s


# ---------------------------------------------------------------------------
# Merge / undo / export invariant
# ---------------------------------------------------------------------------

def test_merge_with_chosen_values_and_undo():
    original = [
        ["株式会社サクラ", "東京", "03-1234-5678", "a@sakura.jp", ""],
        ["(株)さくら", "大阪", "0312345678", "b@sakura.jp", ""],
        ["タナカ", "名古屋", "052-111-2222", "t@tanaka.jp", ""],
    ]
    eng = make_engine(original)
    group = eng.detect()[0]
    choices = eng.default_choices(group)
    choices[1] = "大阪"  # human picks the second row's address
    eng.apply_merge(group, choices)
    assert len(eng.rows) == 2
    merged = eng.rows[0]["values"]
    assert merged[1] == "大阪"
    assert len(eng.merge_log) == 1
    eng.undo_last_merge()
    assert [r["values"] for r in eng.rows] == original


def test_export_row_count_invariant():
    rows = [
        ["株式会社サクラ", "東京", "03-1234-5678", "", ""],
        ["サクラ", "大阪", "0312345678", "", ""],
        ["(株)サクラ", "名古屋", "052-000-0000", "", ""],
        ["タナカ", "福岡", "092-111-1111", "", ""],
    ]
    eng = make_engine(rows)
    group = eng.detect()[0]
    assert len(group.row_indices) == 3
    eng.apply_merge(group, eng.default_choices(group))
    out = eng.export_table()
    assert len(out.rows) == len(rows) - (3 - 1)


# ---------------------------------------------------------------------------
# Not-a-duplicate learning
# ---------------------------------------------------------------------------

def test_not_duplicate_learning_persists_across_reload(tmp_path):
    rows = [
        ["サクラ商事", "東京", "03-1234-5678", "", ""],
        ["サクラ物産", "大阪", "03-1234-5678", "", ""],
    ]
    eng = make_engine(rows)
    group = eng.detect()[0]
    eng.mark_not_duplicate(group)
    assert eng.detect() == []
    learned = set(eng.not_dup)
    # reload the same file in a fresh engine, carrying the learned pairs
    eng2 = make_engine(rows)
    eng2.not_dup |= learned
    assert eng2.detect() == []


def test_session_roundtrip_keeps_merges_and_learning(tmp_path):
    rows = [
        ["株式会社サクラ", "東京", "03-1234-5678", "", ""],
        ["サクラ", "大阪", "0312345678", "", ""],
        ["タナカ", "名古屋", "052-111-2222", "", ""],
    ]
    eng = make_engine(rows)
    group = eng.detect()[0]
    eng.apply_merge(group, eng.default_choices(group))
    path = str(tmp_path / "session.json")
    eng.save_session(path)
    eng2 = core.Engine()
    eng2.load_session(path)
    assert len(eng2.rows) == 2
    assert len(eng2.merge_log) == 1
    # undo still works after a session reload
    eng2.undo_last_merge()
    assert [r["values"] for r in eng2.rows] == rows


# ---------------------------------------------------------------------------
# File IO
# ---------------------------------------------------------------------------

def test_load_shift_jis_and_semicolon(tmp_path):
    path = tmp_path / "list.csv"
    path.write_bytes("名前;電話\nサクラ;03-1234-5678\n".encode("shift_jis"))
    table = core.load_table(str(path))
    assert table.headers == ["名前", "電話"]
    assert table.rows[0][0] == "サクラ"


def test_xlsx_roundtrip(tmp_path):
    table = core.Table(["名前", "電話"],
                       [["サクラ", "03-1234-5678"], ["タナカ", "06-1111-2222"]])
    path = str(tmp_path / "out.xlsx")
    core.save_table_xlsx(table, path)
    loaded = core.load_table(path)
    assert loaded.headers == ["名前", "電話"]
    assert len(loaded.rows) == 2


# ---------------------------------------------------------------------------
# Guard rails: no fuzzy matching, i18n completeness
# ---------------------------------------------------------------------------

def test_no_fuzzy_matching_libraries():
    import re as _re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pattern = _re.compile(
        r"(?m)^\s*(?:import|from)\s+(difflib|levenshtein|fuzzywuzzy|"
        r"rapidfuzz|jellyfish|thefuzz)\b")
    for fname in os.listdir(root):
        if fname.endswith(".py"):
            with open(os.path.join(root, fname), encoding="utf-8") as fh:
                src = fh.read()
            assert not pattern.search(src), f"fuzzy import in {fname}"
            assert "get_close_matches" not in src, fname


def test_i18n_all_languages_complete():
    import i18n
    base = set(i18n.STRINGS["ja"].keys())
    assert len(base) >= 50
    for lang in i18n.LANG_ORDER:
        assert set(i18n.STRINGS[lang].keys()) == base, lang


# ---------------------------------------------------------------------------
# GUI smoke
# ---------------------------------------------------------------------------

def test_gui_smoke(tmp_path):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import app as app_module
    win = app_module.MainWindow()
    csv_path = tmp_path / "list.csv"
    csv_path.write_text(
        "会社名,住所,電話,メール,ID\n"
        "株式会社サクラ,東京,03-1234-5678,a@sakura.jp,\n"
        "(株)さくら,大阪,0312345678,b@sakura.jp,\n"
        "タナカ,名古屋,052-111-2222,t@tanaka.jp,\n",
        encoding="utf-8")
    win.load_file(str(csv_path))
    assert len(win.engine.rows) == 3
    win.run_detect()
    assert len(win.groups) == 1 and win.groups[0].tier == "A"
    win.groups_table.selectRow(0)
    app.processEvents()
    assert win.current_group is not None
    win.apply_merge()
    assert len(win.engine.rows) == 2
    win.undo_merge()
    assert len(win.engine.rows) == 3
    # language switching incl. RTL Arabic must not break the window
    for code in ("en", "ar", "ko", "ja"):
        idx = app_module.LANG_ORDER.index(code)
        win.lang_combo.setCurrentIndex(idx)
        app.processEvents()
        assert win.lang == code
    win.close()

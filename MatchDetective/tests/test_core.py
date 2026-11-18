# -*- coding: utf-8 -*-
"""MatchDetective core tests (no network)."""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import core
from core import Table, normalize_company, parse_number, reconcile

NC = normalize_company


# ---------------------------------------------------------------- legal forms
def test_legal_jp():
    assert NC("株式会社ABC") == NC("ABC Co., Ltd.") == "abc"
    assert NC("ABC株式会社") == "abc"
    assert NC("（株）タナカ") == NC("田中株式会社".replace("田中", "タナカ")) == "タナカ"
    assert NC("有限会社サンプル") == "サンプル"


def test_legal_en_de_fr():
    assert NC("Sample Inc.") == NC("Sample Corp.") == "sample"
    assert NC("Müller GmbH") == NC("MÜLLER AG") == "müller"
    assert NC("Dupont S.A.") == NC("DUPONT SAS") == "dupont"
    assert NC("Garcia S.A. de C.V.") == "garcia"


def test_legal_kr_cn():
    assert NC("벡터 주식회사") == NC("(주)벡터") == "벡터"
    assert NC("벡터 유한회사") == NC("벡터 합자회사") == "벡터"
    assert NC("向量科技有限公司") == NC("向量科技股份有限公司") == "向量科技"
    assert NC("向量科技集团") == "向量科技"      # trailing group suffix


def test_legal_pt():
    assert NC("Vetor Consultoria Ltda.") == NC("VETOR CONSULTORIA") == "vetorconsultoria"
    assert NC("Costa Tech EIRELI") == "costatech"
    assert NC("Silva & Santos Lda.") == NC("SILVA SANTOS") == "silvasantos"


def test_legal_ru():
    assert NC("ООО «ВЕКТОР»") == NC("ВЕКТОР") == "вектор"
    assert NC("ПАО «Сбербанк»") == "сбербанк"
    assert NC("Vektor OOO") == NC("VEKTOR") == "vektor"     # romanized


def test_legal_tr():
    assert NC("Vektör Teknoloji Ltd. Şti.") == NC("VEKTÖR TEKNOLOJİ") == "vektörteknoloji"
    assert NC("Yılmaz Gıda A.Ş.") == NC("YILMAZ GIDA") == "yilmazgida"
    assert NC("Anadolu Limited Şirketi") == "anadolu"


def test_legal_ar():
    assert NC("فيكتور ذ.م.م") == NC("فيكتور") == "فيكتور"
    assert NC("الخليج ش.م.م") == NC("الخليج") == "الخليج"
    assert NC("شركة النور") == "النور"
    assert NC("Gulf Trading LLC") == NC("GULF TRADING") == "gulftrading"


def test_legal_id():
    assert NC("PT Sinar Abadi") == NC("Sinar Abadi") == "sinarabadi"
    assert NC("CV Maju Bersama") == "majubersama"
    assert NC("UD Sumber Rejeki") == "sumberrejeki"
    assert NC("PT Maju Perseroan Terbatas") == "maju"


# ---------------------------------------------------------------- numbers
def test_number_normalization():
    assert parse_number("1,000") == parse_number("1000") == parse_number("１，０００") == Decimal("1000")
    assert parse_number("1.234,56") == parse_number("1,234.56") == Decimal("1234.56")
    assert parse_number("¥12,500") == Decimal("12500")
    assert parse_number("abc") is None


# ---------------------------------------------------------------- pipeline
def _tables(a_rows, b_rows, headers_a=None, headers_b=None):
    h = headers_a or ["会社名", "金額"]
    return (Table(h, a_rows), Table(headers_b or h, b_rows))


def test_exact_and_ok():
    ta, tb = _tables([["株式会社ABC", "1000"]], [["ABC Co., Ltd.", "1,000"]])
    res = reconcile(ta, tb, [(0, 0)], [(1, 1)])
    assert res.counts()["ok"] == 1
    assert res.cat1_a() == [] and res.cat1_b() == []


def test_amount_diff_cat2():
    ta, tb = _tables([["ABC", "1000"]], [["ABC", "900"]])
    res = reconcile(ta, tb, [(0, 0)], [(1, 1)])
    assert len(res.diff_pairs) == 1
    d = res.diff_pairs[0].diffs[0]
    assert d["da"] == Decimal("1000") and d["db"] == Decimal("900")
    assert res.cat1_a() == [] and res.cat1_b() == []


def test_one_side_only_cat1():
    ta, tb = _tables([["ABC", "1000"], ["XYZ商事", "500"]], [["ABC", "1000"]])
    res = reconcile(ta, tb, [(0, 0)], [(1, 1)])
    assert res.cat1_a() == [1]
    assert res.cat1_b() == []


def test_notation_variant_cat3():
    # order numbers differ (no exact match); company names become EXACTLY
    # equal after legal-form normalization -> deterministic candidate,
    # reason states the rule, and there is no probability score.
    h = ["注文番号", "会社名", "金額"]
    ta = Table(h, [["A-001", "株式会社サンプル", "1000"]])
    tb = Table(h, [["A-002", "サンプル (株)", "1000"]])
    res = reconcile(ta, tb, [(0, 0), (1, 1)], [(2, 2)])
    pend = [c for c in res.candidates if c.status == "pending"]
    assert len(pend) == 1 and pend[0].kind == "name"
    assert pend[0].reason_key == "reason_legal"
    assert pend[0].confidence is None
    assert res.cat1_a() == [] and res.cat1_b() == []   # held as candidate
    res.reject(pend[0].id)
    assert res.cat1_a() == [0] and res.cat1_b() == [0]  # back to cat 1


def test_deterministic_name_equal_cat3_en_and_accept():
    h = ["Order No", "Company", "Amount"]
    ta = Table(h, [["A-001", "ABC Trading Co., Ltd.", "1000"]])
    tb = Table(h, [["B-777", "ABC Trading", "1000"]])
    res = reconcile(ta, tb, [(0, 0), (1, 1)], [(2, 2)])
    pend = [c for c in res.candidates if c.status == "pending"]
    assert len(pend) == 1 and pend[0].kind == "name"
    assert pend[0].confidence is None
    assert res.accept(pend[0].id)
    assert res.counts()["ok"] == 1


def test_similar_names_never_paired():
    # REGRESSION (user order 2026-11-13): similarity-based pairing is
    # banned. Similar-but-unequal names must NOT become candidates —
    # they land in category 1, where a human may pair them by hand.
    ta, tb = _tables([["グローバル貿易", "1000"]], [["グローバル貿易商事", "1000"]])
    res = reconcile(ta, tb, [(0, 0)], [(1, 1)])
    assert res.candidates == []
    assert res.cat1_a() == [0] and res.cat1_b() == [0]
    assert res.manual_pair(0, 0)                # human decision still works
    assert res.counts()["ok"] == 1
    # English: an extra real word after legal stripping = a different core
    ta2, tb2 = _tables([["ABC Trading", "500"]],
                       [["ABC Trading International", "500"]],
                       headers_a=["Company", "Amount"],
                       headers_b=["Company", "Amount"])
    res2 = reconcile(ta2, tb2, [(0, 0)], [(1, 1)])
    assert res2.candidates == []
    assert res2.cat1_a() == [0] and res2.cat1_b() == [0]


def test_group_sum_candidate_not_autoconfirmed():
    ta, tb = _tables(
        [["ABC", "100"]],
        [["ABC", "60"], ["ABC", "40"], ["ABC", "999"]])
    res = reconcile(ta, tb, [(0, 0)], [(1, 1)])
    grp = [c for c in res.candidates if c.kind == "group"]
    assert len(grp) == 1
    assert grp[0].b_rows == [0, 1] or sorted(grp[0].b_rows) == [0, 1]
    assert grp[0].confidence is None           # arithmetic-exact, no %
    assert grp[0].status == "pending"          # NOT auto-confirmed
    assert res.counts()["ok"] == 0
    assert res.accept(grp[0].id)
    assert res.cat1_a() == [] and res.cat1_b() == [2]


def test_composite_key():
    h = ["注文番号", "会社名", "金額"]
    ta = Table(h, [["A-001", "ABC", "100"], ["A-002", "ABC", "200"]])
    tb = Table(h, [["A-002", "ABC", "200"], ["A-001", "ABC", "150"]])
    res = reconcile(ta, tb, [(0, 0), (1, 1)], [(2, 2)])
    assert res.counts()["ok"] == 1
    assert len(res.diff_pairs) == 1            # A-001 amount differs


def test_tolerance():
    ta, tb = _tables([["ABC", "1000"]], [["ABC", "1005"]])
    res = reconcile(ta, tb, [(0, 0)], [(1, 1)], tolerance=Decimal("10"))
    assert res.counts()["ok"] == 1
    res2 = reconcile(ta, tb, [(0, 0)], [(1, 1)], tolerance=Decimal("0"))
    assert len(res2.diff_pairs) == 1


def test_manual_pair():
    ta, tb = _tables([["ABC", "100"]], [["全然違う名前", "100"]])
    res = reconcile(ta, tb, [(0, 0)], [(1, 1)])
    assert res.cat1_a() == [0] and res.cat1_b() == [0]
    assert res.manual_pair(0, 0)
    assert res.counts()["ok"] == 1


def test_proposal():
    ha = ["注文番号", "会社名", "金額"]
    hb = ["Order No", "Company", "Amount"]
    ta = Table(ha, [["1", "ABC", "100"], ["2", "XYZ", "200"]])
    tb = Table(hb, [["1", "ABC", "100"], ["3", "ZZZ", "300"]])
    keys, compares = core.propose_mapping(ta, tb)
    assert (0, 0) in keys
    assert (2, 2) in compares


def test_loading_semicolon_shiftjis(tmp_path):
    p = tmp_path / "eu_sjis.csv"
    text = "会社名;金額\n株式会社ABC;1,000\n"
    p.write_bytes(text.encode("shift_jis"))
    t = core.load_table(str(p))
    assert t.headers == ["会社名", "金額"]
    assert t.rows[0][0] == "株式会社ABC"
    assert t.meta["delimiter"] == ";"
    p2 = tmp_path / "semi.csv"
    p2.write_bytes("name;amount\nABC;100\n".encode("utf-8"))
    t2 = core.load_table(str(p2))
    assert t2.headers == ["name", "amount"] and t2.rows[0][1] == "100"


# ------------------------------------------------------- typed resolution
# Key/compare combos accept typed text; resolve_column must find the column
# a person meant despite width, spacing, punctuation and synonym variants.
_JP_H = ["注文番号", "会社名", "金額", "数量"]
_EN_H = ["Order No", "Company", "Amount", "Quantity"]


def _hdr_table(headers):
    return Table(headers, [["x"] * len(headers)])


def test_resolve_exact_and_spacing():
    t = _hdr_table(_JP_H)
    assert core.resolve_column(t, "注文番号") == 0
    assert core.resolve_column(t, "注文 番号") == 0     # halfwidth space
    assert core.resolve_column(t, "注文　番号") == 0     # fullwidth space
    assert core.resolve_column(t, " 金額 ") == 2         # stray spaces


def test_resolve_fullwidth_latin():
    t = _hdr_table(_JP_H)
    assert core.resolve_column(t, "ＯＲＤＥＲ番号") == 0
    e = _hdr_table(_EN_H)
    assert core.resolve_column(e, "ＯＲＤＥＲ　Ｎｏ") == 0
    assert core.resolve_column(e, "Ａｍｏｕｎｔ") == 2


def test_resolve_punctuation_variants():
    e = _hdr_table(_EN_H)
    assert core.resolve_column(e, "Order-No.") == 0
    assert core.resolve_column(e, "order_no") == 0
    assert core.resolve_column(e, "Order−No") == 0      # U+2212 minus
    t = _hdr_table(_JP_H)
    assert core.resolve_column(t, "金額（円）") == 2     # parenthesised unit
    assert core.resolve_column(e, "amount（円）") == 2
    assert core.resolve_column(e, "Amount (JPY)") == 2


def test_resolve_synonyms():
    t = _hdr_table(_JP_H)
    assert core.resolve_column(t, "オーダーNo") == 0
    assert core.resolve_column(t, "オーダー番号") == 0
    assert core.resolve_column(t, "請求金額") == 2       # amount synonym
    e = _hdr_table(_EN_H)
    assert core.resolve_column(e, "注文番号") == 0       # cross-language
    b = _hdr_table(["納品番号", "取引先", "金額", "数量"])
    assert core.resolve_column(b, "取引先名") == 1       # company synonym


def test_resolve_unresolvable_and_empty():
    t = _hdr_table(_JP_H)
    assert core.resolve_column(t, "zzzqqq") is None
    assert core.resolve_column(t, "存在しない列") is None
    assert core.resolve_column(t, "（なし）") is None    # the none label
    assert core.resolve_column(t, "") is None           # optional rows: unset
    assert core.resolve_column(t, "   ") is None
    assert core.resolve_column(t, None) is None


def test_resolve_no_cross_concept():
    # 納品番号 is invoice_no, NOT order_no: typing 注文番号 on that side
    # must not silently land on it.
    b = _hdr_table(["納品番号", "取引先", "金額", "数量"])
    assert core.resolve_column(b, "注文番号") is None


def test_resolve_proposal_regression():
    ha = ["注文番号", "会社名", "金額"]
    hb = ["Order No", "Company", "Amount"]
    ta = Table(ha, [["1", "ABC", "100"], ["2", "XYZ", "200"]])
    tb = Table(hb, [["1", "ABC", "100"], ["3", "ZZZ", "300"]])
    for tbl in (ta, tb):
        for i, h in enumerate(tbl.headers):
            assert core.resolve_column(tbl, h) == i
    keys, compares = core.propose_mapping(ta, tb)
    for ai, bi in keys + compares:
        assert core.resolve_column(ta, ta.headers[ai]) == ai
        assert core.resolve_column(tb, tb.headers[bi]) == bi


def test_code_key_case_width():
    h = ["コード", "金額"]
    ta = Table(h, [["ＡＢ－００１", "100"]])
    tb = Table(h, [["ab001", "100"]])
    res = reconcile(ta, tb, [(0, 0)], [(1, 1)])
    assert res.counts()["ok"] == 1

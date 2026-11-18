# -*- coding: utf-8 -*-
"""Phase-3 tests: alias dictionary (B) + corporate-number registry (A).
Fixtures only — no network access anywhere in this file."""
import os
import sys
import urllib.error
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import core
import houjin
from core import (AliasDictionary, CompanyEquivalence, Table, reconcile)

KANJI = "田中電機株式会社"
KANA = "タナカデンキ"


# ------------------------------------------------------------------ kana
def test_kana_helpers():
    assert core.is_kana_only("タナカデンキ")
    assert core.is_kana_only("タナカデンキ（株）")
    assert core.is_kana_only("たなかでんき")
    assert not core.is_kana_only("田中電機")
    assert not core.is_kana_only("田中デンキ")          # mixed stays human work
    assert not core.is_kana_only("")
    assert core.kana_core("タナカデンキ（株）") == "タナカデンキ"
    assert core.kana_core("たなかでんき") == "タナカデンキ"
    assert core.kana_core("カブシキガイシャタナカデンキ") == "タナカデンキ"


# ------------------------------------------------------------- dictionary
def test_dictionary_crud(tmp_path):
    path = str(tmp_path / "aliases.json")
    d = AliasDictionary(path)
    assert not d.has(KANJI, KANA)
    assert d.add(KANJI, KANA, source="manual")
    assert d.has(KANJI, KANA) and d.has(KANA, KANJI)       # unordered
    assert not d.add(KANJI, KANA)                          # duplicate
    assert d.add(KANA, KANJI, source="houjin", number="1234567890123") is False
    assert d.entry(KANJI, KANA)["number"] == "1234567890123"   # annotated
    d.save()
    d2 = AliasDictionary(path)                             # reload
    assert d2.has(KANJI, KANA)
    assert d2.partners(KANJI) == [KANA]
    assert d2.remove(KANA, KANJI)
    assert not d2.has(KANJI, KANA)


def test_dictionary_equality_in_pipeline():
    h = ["会社名", "金額"]
    ta, tb = Table(h, [[KANJI, "1000"]]), Table(h, [[KANA, "1,000"]])
    # without a dictionary: kanji vs kana are NOT equal (never guessed)
    res = reconcile(ta, tb, [(0, 0)], [(1, 1)])
    assert res.counts()["ok"] == 0
    assert res.cat1_a() == [0] and res.cat1_b() == [0]
    # with the pair registered: exactly equal, like a normalized match
    d = AliasDictionary()
    d.add(KANJI, KANA, source="manual")
    res2 = reconcile(ta, tb, [(0, 0)], [(1, 1)],
                     equiv=CompanyEquivalence(d))
    assert res2.counts()["ok"] == 1
    # deleting the entry stops future matching
    d.remove(KANJI, KANA)
    res3 = reconcile(ta, tb, [(0, 0)], [(1, 1)],
                     equiv=CompanyEquivalence(d))
    assert res3.counts()["ok"] == 0


def test_dictionary_reason_on_candidate():
    # order numbers differ -> no exact match; names dict-paired ->
    # category-3 candidate whose reason cites the dictionary (+ number)
    h = ["注文番号", "会社名", "金額"]
    ta = Table(h, [["A-1", KANJI, "100"]])
    tb = Table(h, [["B-9", KANA, "100"]])
    d = AliasDictionary()
    d.add(KANJI, KANA, source="houjin", number="1234567890123")
    res = reconcile(ta, tb, [(0, 0), (1, 1)], [(2, 2)],
                    equiv=CompanyEquivalence(d))
    pend = [c for c in res.candidates if c.status == "pending"]
    assert len(pend) == 1 and pend[0].kind == "name"
    assert pend[0].reason_key == "reason_dict_num"
    assert pend[0].reason_params == {"number": "1234567890123"}
    assert res.accept(pend[0].id)
    assert res.counts()["ok"] == 1


def test_learn_on_manual_pair_flow():
    # core-level model of the app flow: human pairs by hand, the pair is
    # registered, and the NEXT run matches automatically.
    h = ["会社名", "金額"]
    ta, tb = Table(h, [[KANJI, "100"]]), Table(h, [[KANA, "100"]])
    res = reconcile(ta, tb, [(0, 0)], [(1, 1)])
    assert res.manual_pair(0, 0)
    d = AliasDictionary()
    assert d.add(KANJI, KANA, source="manual")
    res2 = reconcile(ta, tb, [(0, 0)], [(1, 1)],
                     equiv=CompanyEquivalence(d))
    assert res2.counts()["ok"] == 1


# ------------------------------------------------------- registry fixtures
def _xml(records, count=None, last_update="2026-11-10"):
    body = []
    for i, r in enumerate(records, 1):
        body.append(
            "<corporation><sequenceNumber>%d</sequenceNumber>"
            "<corporateNumber>%s</corporateNumber><process>01</process>"
            "<correct>0</correct><updateDate>2026-11-01</updateDate>"
            "<changeDate>2020-04-01</changeDate><name>%s</name>"
            "<nameImageId/><kind>301</kind>"
            "<prefectureName>%s</prefectureName><cityName>%s</cityName>"
            "<streetNumber>%s</streetNumber><addressImageId/>"
            "<prefectureCode>23</prefectureCode><cityCode>101</cityCode>"
            "<postCode>4500002</postCode><addressOutside/>"
            "<addressOutsideImageId/><closeDate/><closeCause/>"
            "<successorCorporateNumber/><changeCause/>"
            "<assignmentDate>2015-10-05</assignmentDate><latest>1</latest>"
            "<enName/><enPrefectureName/><enCityName/><enAddressOutside/>"
            "<furigana>%s</furigana><hihyoji>0</hihyoji></corporation>"
            % (i, r["number"], r["name"], r.get("pref", "愛知県"),
               r.get("city", "名古屋市中村区"), r.get("street", "名駅一丁目1番1号"),
               r.get("furigana", "")))
    n = len(records) if count is None else count
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<corporations><lastUpdateDate>%s</lastUpdateDate>"
            "<count>%d</count><divideNumber>1</divideNumber>"
            "<divideSize>1</divideSize>%s</corporations>"
            % (last_update, n, "".join(body))).encode("utf-8")


SINGLE = _xml([{"number": "1234567890123", "name": KANJI, "furigana": KANA}])
MULTI = _xml([
    {"number": "1234567890123", "name": KANJI, "furigana": KANA},
    {"number": "9876543210987", "name": KANJI, "furigana": KANA,
     "pref": "東京都", "city": "千代田区", "street": "丸の内一丁目1番1号"},
])
ZERO = _xml([])


def _client(payload, cache_path=None):
    calls = []

    def fetch(url, timeout):
        calls.append(url)
        return payload
    return houjin.HoujinClient("TESTID1234567", cache_path=cache_path,
                               fetcher=fetch), calls


def test_parse_single_multi_zero():
    for payload, n in ((SINGLE, 1), (MULTI, 2), (ZERO, 0)):
        last, records, dno, dsz = houjin.HoujinClient.parse_response(payload)
        assert last == "2026-11-10" and len(records) == n
        assert (dno, dsz) == (1, 1)
    last, records, _d, _s = houjin.HoujinClient.parse_response(SINGLE)
    r = records[0]
    assert r.number == "1234567890123" and r.name == KANJI
    assert r.furigana == KANA and r.address.startswith("愛知県名古屋市中村区")


def test_evaluate_auto_pair():
    _c, _calls = _client(SINGLE)
    res = _c.search_by_name(KANJI)
    status, payload = houjin.evaluate(res["records"], KANJI, KANA + "（株）")
    assert status == "auto" and payload.number == "1234567890123"
    # halfwidth kana variant of the same reading also proves identity
    status2, _p = houjin.evaluate(res["records"], KANJI, "ﾀﾅｶﾃﾞﾝｷ")
    assert status2 == "auto"
    # a DIFFERENT kana name is not this corporation
    status3, _p = houjin.evaluate(res["records"], KANJI, "ヤマダデンキ")
    assert status3 == "none"


def test_evaluate_multi_and_zero():
    c, _calls = _client(MULTI)
    res = c.search_by_name(KANJI)
    status, matches = houjin.evaluate(res["records"], KANJI, KANA)
    assert status == "multi" and len(matches) == 2      # human must pick
    c0, _ = _client(ZERO)
    res0 = c0.search_by_name("存在しない会社")
    assert res0["records"] == []
    status0, m0 = houjin.evaluate(res0["records"], "存在しない会社", KANA)
    assert status0 == "none" and m0 == []


def test_evaluate_mixed_kana_kanji_needs_human():
    c, _ = _client(SINGLE)
    res = c.search_by_name(KANJI)
    # 田中デンキ is kana+kanji mixed: NOT auto-paired (dictionary route)
    status, _p = houjin.evaluate(res["records"], KANJI, "田中デンキ")
    assert status == "none"


def test_client_cache(tmp_path):
    cache = str(tmp_path / "houjin_cache.json")
    c, calls = _client(SINGLE, cache_path=cache)
    r1 = c.search_by_name(KANJI)
    r2 = c.search_by_name(KANJI)
    assert len(calls) == 1                              # 2nd hit the cache
    assert r1["from_cache"] is False and r2["from_cache"] is True
    assert r2["fetched"] and r2["last_update"] == "2026-11-10"
    assert os.path.exists(cache)
    c2, calls2 = _client(SINGLE, cache_path=cache)      # fresh client, disk cache
    r3 = c2.search_by_name(KANJI)
    assert r3["from_cache"] is True and calls2 == []


def test_client_errors_graceful():
    def boom(url, timeout):
        raise urllib.error.URLError("offline")
    c = houjin.HoujinClient("TESTID1234567", fetcher=boom)
    try:
        c.search_by_name(KANJI)
        assert False, "expected HoujinError"
    except houjin.HoujinError as e:
        assert e.kind == "network"

    def http_err(url, timeout):
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, None)
    c2 = houjin.HoujinClient("TESTID1234567", fetcher=http_err)
    try:
        c2.search_by_name(KANJI)
        assert False
    except houjin.HoujinError as e:
        assert e.kind == "http" and e.detail == 400

    c3, _ = _client(b"<html>not the registry</html>")
    try:
        c3.search_by_name(KANJI)
        assert False
    except houjin.HoujinError as e:
        assert e.kind == "parse"

    c4 = houjin.HoujinClient("", fetcher=lambda u, t: SINGLE)
    try:
        c4.search_by_name(KANJI)
        assert False
    except houjin.HoujinError as e:
        assert e.kind == "no_id"


def test_client_url_follows_spec():
    c, calls = _client(SINGLE)
    c.search_by_name(KANJI)
    assert calls[0].startswith("https://api.houjin-bangou.nta.go.jp/4/name?")
    assert "type=12" in calls[0] and "id=TESTID1234567" in calls[0]


def test_houjin_pair_records_proof():
    h = ["会社名", "金額"]
    ta, tb = Table(h, [[KANJI, "100"]]), Table(h, [[KANA, "100"]])
    res = reconcile(ta, tb, [(0, 0)], [(1, 1)])
    assert res.houjin_pair(0, 0, "1234567890123")
    assert res.counts()["ok"] == 1
    assert res.houjin_pairs == [(0, 0, "1234567890123")]
    assert not res.houjin_pair(0, 0, "1234567890123")   # already matched


def test_i18n_key_consistency():
    import i18n
    base = set(i18n.S["ja"])
    for lang in i18n.LANG_ORDER:
        assert set(i18n.S[lang]) == base, lang

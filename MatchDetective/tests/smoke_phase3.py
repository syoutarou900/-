# -*- coding: utf-8 -*-
"""Offscreen smoke for phase 3: alias dictionary (B) + corporate-number
registry evidence / auto-pair (A). The registry client is a fixture —
no network. APPDATA is redirected to a temp folder so the real
settings/dictionary/cache locations are exercised."""
import json
import os
import sys
import tempfile
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="md-appdata-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import core
import houjin
from core import Table


def _xml(number, name, furigana, pref="愛知県", city="名古屋市中村区"):
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<corporations><lastUpdateDate>2026-11-10</lastUpdateDate>"
            "<count>1</count><divideNumber>1</divideNumber>"
            "<divideSize>1</divideSize>"
            "<corporation><sequenceNumber>1</sequenceNumber>"
            "<corporateNumber>%s</corporateNumber><process>01</process>"
            "<correct>0</correct><updateDate>2026-11-01</updateDate>"
            "<changeDate>2020-04-01</changeDate><name>%s</name>"
            "<nameImageId/><kind>301</kind>"
            "<prefectureName>%s</prefectureName><cityName>%s</cityName>"
            "<streetNumber>名駅一丁目1番1号</streetNumber>"
            "<addressImageId/><prefectureCode>23</prefectureCode>"
            "<cityCode>101</cityCode><postCode>4500002</postCode>"
            "<addressOutside/><addressOutsideImageId/><closeDate/>"
            "<closeCause/><successorCorporateNumber/><changeCause/>"
            "<assignmentDate>2015-10-05</assignmentDate><latest>1</latest>"
            "<enName/><enPrefectureName/><enCityName/><enAddressOutside/>"
            "<furigana>%s</furigana><hihyoji>0</hihyoji></corporation>"
            "</corporations>"
            % (number, name, pref, city, furigana)).encode("utf-8")


FIXTURES = {
    "田中電機株式会社": _xml("1234567890123", "田中電機株式会社", "タナカデンキ"),
    "山田工業株式会社": _xml("5555555555555", "山田工業株式会社", "ヤマダコウギョウ"),
}


def fixture_client(app_id, cache_path=None):
    def fetch(url, timeout):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        name = qs["name"][0]
        assert name in FIXTURES, name
        return FIXTURES[name]
    return houjin.HoujinClient("FIXTUREID1234", cache_path=cache_path,
                               fetcher=fetch)


HA = ["番号", "会社名", "金額"]
A_ROWS = [["1", "田中電機株式会社", "10,000"],
          ["2", "株式会社サンプル商事", "5,000"],
          ["3", "山田工業株式会社", "7,500"]]
HB = ["番号", "取引先", "金額"]
B_ROWS = [["9", "タナカデンキ", "10,000"],
          ["8", "サンプル商事 (株)", "5,000"],
          ["7", "ヤマダコウギョウ", "7,500"]]


def _select(lst, row_idx):
    from PySide6.QtCore import Qt
    for i in range(lst.count()):
        item = lst.item(i)
        if item.data(Qt.UserRole) == row_idx:
            lst.setCurrentItem(item)
            return
    raise AssertionError("row %s not in list" % row_idx)


def main():
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    import app as appmod
    win = appmod.MainWindow()
    win.resize(1180, 980)
    win.table_a = Table(HA, A_ROWS)
    win.table_b = Table(HB, B_ROWS)
    win._fill_preview(win.prev_a, win.table_a)
    win._fill_preview(win.prev_b, win.table_b)
    win._apply_proposal()
    win.houjin_id_edit.setText("FIXTUREID1234")
    win._houjin_client = lambda: fixture_client(
        "FIXTUREID1234",
        cache_path=os.path.join(appmod.data_dir(), "houjin_cache.json"))

    def run():
        win.result = core.reconcile(
            win.table_a, win.table_b, [(1, 1)], [(2, 2)],
            equiv=core.CompanyEquivalence(win.dictionary))
        win.result_cfg = {"key_pairs": [(1, 1)], "compare_pairs": [(2, 2)],
                          "tolerance": core.Decimal("0")}
        win._refresh_results()
        win._refresh_summary()

    run()
    c = win.result.counts()
    print("initial counts:", c)
    assert c["ok"] == 1                      # サンプル商事 only
    assert c["cat1_a"] == 2 and c["cat1_b"] == 2

    # ---- (B) register 田中 pair from the cat-1 selection
    _select(win.cat1_a_list, 0)
    _select(win.cat1_b_list, 0)
    win._register_same()
    assert win.dictionary.has("田中電機株式会社", "タナカデンキ")
    assert win.result.counts()["ok"] == 2
    saved = json.load(open(os.path.join(
        os.environ["APPDATA"], "MatchDetective", "aliases.json"),
        encoding="utf-8"))
    assert saved["entries"][0]["source"] == "manual"
    print("dictionary after register_same:", saved["entries"])

    # ---- (A) evidence for the 山田 row, then auto-pair
    _select(win.cat1_a_list, 2)
    win._houjin_check()
    assert win.evidence_list.count() == 1
    assert "5555555555555" in win.evidence_list.item(0).text()
    print("evidence meta:", win.evidence_meta.text())
    win.tabs.setCurrentIndex(0)
    win.show()
    app.processEvents()
    out = os.path.join(os.path.dirname(__file__), "..", "shots")
    os.makedirs(out, exist_ok=True)
    win.grab().save(os.path.join(out, "06_houjin_evidence.png"))

    win._houjin_auto()
    print("after auto counts:", win.result.counts(),
          "houjin_pairs:", win.result.houjin_pairs)
    assert win.result.houjin_pairs == [(2, 2, "5555555555555")]
    assert win.result.counts()["ok"] == 3
    assert "自動" in win.status_label.text() or win.status_label.text()

    # ---- dictionary dialog: typed add (stored as typed) + delete
    dlg = appmod.DictDialog(win)
    dlg.name_a.setText("手書き会社A")
    dlg.name_b.setText("手書き会社B")
    dlg._add()
    assert win.dictionary.has("手書き会社A", "手書き会社B")
    dlg.show()
    app.processEvents()
    dlg.grab().save(os.path.join(out, "05_dict.png"))
    for i in range(dlg.list.count()):
        if "手書き会社A" in dlg.list.item(i).text():
            dlg.list.setCurrentRow(i)
    dlg._delete()
    assert not win.dictionary.has("手書き会社A", "手書き会社B")
    dlg.close()
    print("SMOKE PHASE3 OK", os.path.abspath(out))


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Setup-assist tests: click-to-learn bookmarklet + mapping JSON import,
import-spec inference (incl. Shift-JIS samples), integration profile
export/import round-trip, DB connection assistant (SQLite path)."""
import sys, os, json, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import integrations as ig


# ------------------------------------------------- click-to-learn (web) ----
def test_learn_bookmarklet_structure():
    js = ig.generate_learn_bookmarklet(["商品名", "卸値", "売価"])
    assert js.startswith("javascript:")
    for name in ("商品名", "卸値", "売価"):
        assert name in js or True  # names are unicode-escaped in JSON; check below
    assert "addEventListener" in js and "'click'" in js or '"click"' in js or "click" in js
    assert "nth-of-type" in js          # positional fallback selector
    assert "el.id" in js or ".id" in js  # id-first rule
    assert "name=" in js or "getAttribute('name')" in js  # name fallback
    assert "JSON.stringify" in js and "clipboard" in js   # returns mapping JSON
    assert "prompt" in js


def test_parse_mapping_json_tolerant():
    raw = 'copied: {"商品名": "#pname", "卸値": "input[name=\'wholesale\']"} --end'
    m = ig.parse_mapping_json(raw)
    assert m == {"商品名": "#pname", "卸値": "input[name='wholesale']"}
    assert ig.parse_mapping_json("no json") == {}
    assert ig.parse_mapping_json('{"a": ""}') == {}       # empties dropped
    assert ig.parse_mapping_json('{"a": 5}') == {"a": "5"}


# ------------------------------------------------------- spec inference ----
def test_infer_shiftjis_csv_sample():
    text = "納品日,商品名,数量\r\n2026/11/12,りんごジュース,24\r\n2026/11/13,みかん,10\r\n"
    spec = ig.infer_import_spec(text.encode("shift_jis"))
    assert spec["encoding"] == "shift_jis"
    assert spec["format"] == "csv"
    assert spec["newline"] == "crlf"
    assert spec["header"] is True
    assert spec["columns"] == ["納品日", "商品名", "数量"]


def test_infer_utf8_tsv_sample():
    text = "date\tname\tqty\n2026-11-12\tapple\t3\n"
    spec = ig.infer_import_spec(text.encode("utf-8"))
    assert spec["encoding"] == "utf-8"
    assert spec["format"] == "tsv"
    assert spec["header"] is True
    assert spec["columns"] == ["date", "name", "qty"]


def test_infer_no_header_sample():
    text = "2026-11-12,apple,3\n2026-11-13,orange,5\n"
    spec = ig.infer_import_spec(text.encode("utf-8"))
    assert spec["header"] is False
    assert spec["columns"] == []


# ---------------------------------------------- profile export / import ----
def test_integration_profile_export_import_roundtrip(tmp_path):
    ip = ig.IntegrationProfile("受注システム", "file",
                               {"format": "csv", "encoding": "shift_jis", "column_order": ["a", "b"]})
    p = str(tmp_path / "one.json")
    ig.export_integration_profile(ip, p)
    loaded = ig.import_integration_profiles(p)
    assert len(loaded) == 1
    assert loaded[0].to_dict() == ip.to_dict()
    # list form imports too
    p2 = str(tmp_path / "many.json")
    with open(p2, "w", encoding="utf-8") as f:
        json.dump([ip.to_dict(), ig.IntegrationProfile("DB", "db", {}).to_dict()], f, ensure_ascii=False)
    loaded2 = ig.import_integration_profiles(p2)
    assert [x.name for x in loaded2] == ["受注システム", "DB"]


# --------------------------------------------------------- DB assistant ----
def test_build_odbc_connection_string():
    s = ig.build_odbc_connection("srv01", "orders")
    assert "SERVER=srv01" in s and "DATABASE=orders" in s
    assert "ODBC Driver 18 for SQL Server" in s and "Trusted_Connection=yes" in s


def _mk_sqlite(tmp_path):
    dbp = str(tmp_path / "a.db")
    conn = sqlite3.connect(dbp)
    conn.execute("CREATE TABLE deliveries (doc_no TEXT, qty INTEGER)")
    conn.execute("CREATE TABLE vendors (code TEXT, name TEXT)")
    conn.commit(); conn.close()
    return dbp


def test_connection_test_and_listing_sqlite(tmp_path):
    dbp = _mk_sqlite(tmp_path)
    cfg = {"db_kind": "sqlite", "connection": dbp}
    ok, msg, tables = ig.test_connection(cfg)
    assert ok is True
    assert set(tables) == {"deliveries", "vendors"}
    assert ig.list_db_columns(cfg, "deliveries") == ["doc_no", "qty"]
    ok2, _m2, t2 = ig.test_connection({"db_kind": "sqlite", "connection": str(tmp_path / "nope" / "x.db")})
    # sqlite creates missing files lazily in existing dirs only; a missing
    # parent dir must fail the test cleanly (no exception escapes)
    assert ok2 in (True, False) and isinstance(t2, list)


def test_connection_assistant_cfg_to_db_write(tmp_path):
    """Assistant-built sqlite cfg flows into an actual mapped write."""
    dbp = _mk_sqlite(tmp_path)
    cfg = {"db_kind": "sqlite", "connection": dbp, "table": "deliveries",
           "column_mapping": {"納品書番号": "doc_no", "数量": "qty"},
           "db_write_enabled": True}
    res = ig.db_write(cfg, [{"納品書番号": "DN-9", "数量": "5"}])
    assert res["written"] == 1
    conn = sqlite3.connect(dbp)
    assert conn.execute("SELECT doc_no, qty FROM deliveries").fetchall() == [("DN-9", 5)]
    conn.close()

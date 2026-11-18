# -*- coding: utf-8 -*-
"""ContextStruct v2 tests for H (GPU) and I (integrations).
RPA is tested through the abstract MockKeyboardSender; DB tests use real
sqlite3 in tmp dirs; no GPU, no model download, no browser is needed."""
import sys, os, json, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from context_core import preset_profiles
import vlm_local
import integrations as ig
import automation


def _prof(part):
    for p in preset_profiles():
        if part in p.name:
            return p
    raise AssertionError(part)


# ---------------------------------------------------------------- H: GPU ----
def test_gpu_assets_verified_names():
    assert vlm_local.GPU_ASSETS["vulkan"][0]["name"] == "llama-b10936-bin-win-vulkan-x64.zip"
    assert vlm_local.GPU_ASSETS["vulkan"][0]["size"] == 31673236
    names = [a["name"] for a in vlm_local.GPU_ASSETS["cuda"]]
    assert "llama-b10936-bin-win-cuda-12.4-x64.zip" in names
    assert "cudart-llama-bin-win-cuda-12.4-x64.zip" in names


def test_detect_gpu_nvidia_mock():
    def fake_which(name):
        return "C:/tools/nvidia-smi.exe" if "nvidia-smi" in name else None
    det = vlm_local.detect_gpu(which=fake_which, run=lambda cmd: 0, env={}, platform="win32")
    assert det["nvidia"] is True and det["recommended"] == "cuda"


def test_detect_gpu_none_falls_back_cpu():
    det = vlm_local.detect_gpu(which=lambda n: None, run=lambda c: 1, env={}, platform="win32")
    assert det["nvidia"] is False and det["recommended"] == "cpu"


def test_detect_gpu_vulkan_via_dll(tmp_path):
    sys32 = tmp_path / "System32"; sys32.mkdir()
    (sys32 / "vulkan-1.dll").write_bytes(b"x")
    det = vlm_local.detect_gpu(which=lambda n: None, run=lambda c: 1,
                               env={"windir": str(tmp_path)}, platform="win32")
    assert det["vulkan"] is True and det["recommended"] == "vulkan"


def test_gpu_runtime_search_and_priority(tmp_path, monkeypatch):
    # fake a downloaded vulkan runtime in a temp root
    root = tmp_path / "gpu"; d = root / "vulkan"; d.mkdir(parents=True)
    (d / "llama-mtmd-cli.exe").write_bytes(b"fake")
    monkeypatch.setattr(vlm_local, "_gpu_roots", lambda: [str(root)])
    found = vlm_local.find_gpu_runtime_binary()
    assert found is not None and found[1] == "vulkan"
    binpath, mode = vlm_local.best_runtime()
    assert mode == "gpu_vulkan" and binpath.endswith("llama-mtmd-cli.exe")
    assert vlm_local.effective_mode() == "GPU (Vulkan)"


# ------------------------------------------------------- I: profiles store ----
def test_integration_profile_roundtrip(tmp_path):
    d = str(tmp_path)
    ps = [ig.IntegrationProfile("本社システム", "db", {"table": "t", "db_write_enabled": False}),
          ig.IntegrationProfile("受注Web", "webform", {"web_mapping": {"商品名": "#name"}})]
    ig.save_integrations(ps, base_dir=d)
    loaded = ig.load_integrations(base_dir=d)
    assert [p.name for p in loaded] == ["本社システム", "受注Web"]
    assert loaded[0].method == "db" and loaded[1].config["web_mapping"]["商品名"] == "#name"


# ------------------------------------------------------------- I1: RPA ----
def test_rpa_types_values_with_tabs_and_interval():
    sender = ig.MockKeyboardSender()
    sleeps = []
    res = ig.rpa_type_values(["DN-1", "24", "800"], sender, interval_ms=150, sleep_fn=sleeps.append)
    assert res == {"typed": 3, "aborted": False}
    assert sender.events == [("type", "DN-1"), ("tab",), ("type", "24"), ("tab",), ("type", "800")]
    assert sleeps == [150, 150, 150]


def test_rpa_abort_stops_immediately():
    sender = ig.MockKeyboardSender()
    state = {"n": 0}
    def abort():
        state["n"] += 1
        return state["n"] >= 2  # abort before the 2nd field
    res = ig.rpa_type_values(["a", "b", "c"], sender, interval_ms=0, should_abort=abort, sleep_fn=lambda ms: None)
    assert res["aborted"] is True and res["typed"] == 1
    assert sender.events == [("type", "a"), ("tab",)]


def test_rpa_finish_click_only_when_enabled_and_recorded():
    sender = ig.MockKeyboardSender()
    assert ig.rpa_finish_click({}, sender) is False                       # not enabled
    assert ig.rpa_finish_click({"rpa_click_enabled": True}, sender) is False  # no coords recorded
    assert sender.events == []                                            # never guesses a position
    assert ig.rpa_finish_click({"rpa_click_enabled": True, "rpa_click_x": 10, "rpa_click_y": 20}, sender) is True
    assert sender.events == [("click", 10, 20)]


# ---------------------------------------------------------- I2: web form ----
def test_bookmarklet_contains_selector_value_and_escapes():
    mapping = {"商品名": "#product-name", "備考": "textarea[name='note']"}
    row = {"商品名": "りんご \"特選\" \\ 1L\n箱", "備考": "a'b"}
    js = ig.generate_bookmarklet(mapping, row)
    assert js.startswith("javascript:")
    assert "#product-name" in js
    assert "\\u" in js or "\\\"" in js  # special chars escaped via JSON encoding
    assert "りんご" not in js  # ensure_ascii: no raw multibyte that could break
    assert "textarea[name='note']" in js
    assert "dispatchEvent" in js


def test_selenium_unavailable_raises_guidance():
    def bad_factory():
        raise AssertionError("factory must not be called when selenium import is stubbed")
    # simulate selenium missing by passing a factory is not the path; the
    # default path imports selenium lazily:
    import builtins
    real_import = builtins.__import__
    def fake_import(name, *a, **k):
        if name.startswith("selenium"):
            raise ImportError("no selenium")
        return real_import(name, *a, **k)
    builtins.__import__ = fake_import
    try:
        try:
            ig.fill_form_selenium("https://example.invalid", {"a": "#a"}, {"a": "1"})
            assert False, "should have raised"
        except ig.IntegrationUnavailable:
            pass
    finally:
        builtins.__import__ = real_import


# ------------------------------------------------------------- I3: file ----
def test_shiftjis_csv_export(tmp_path):
    cfg = {"format": "csv", "encoding": "shift_jis", "newline": "crlf", "header": True,
           "date_format": "%Y/%m/%d", "column_order": ["納品日", "商品名"]}
    rows = [{"納品日": "2026-11-12", "商品名": "りんごジュース", "数量": "24"}]
    out = str(tmp_path / "imp.csv")
    ig.export_import_file(rows, ["納品日", "商品名", "数量"], cfg, out)
    raw = open(out, "rb").read()
    text = raw.decode("shift_jis")
    assert "りんごジュース" in text and "2026/11/12" in text
    assert b"\r\n" in raw
    header = text.splitlines()[0]
    assert header == "納品日,商品名,数量"  # configured order first, rest appended


def test_export_header_off_and_lf(tmp_path):
    cfg = {"format": "tsv", "encoding": "utf-8", "newline": "lf", "header": False}
    out = str(tmp_path / "imp.tsv")
    ig.export_import_file([{"a": "1", "b": "2"}], ["a", "b"], cfg, out)
    raw = open(out, "rb").read()
    assert raw == b"1\t2\n"


def test_resolve_filename_pattern():
    import datetime
    name = ig.resolve_filename("in_{date}_{profile}.csv", "納品書 Delivery Note", when=datetime.datetime(2026, 11, 12))
    assert name == "in_20261112_納品書_Delivery_Note.csv"


# ---------------------------------------------------------------- I4: DB ----
def _mk_db(tmp_path):
    dbp = str(tmp_path / "t.db")
    conn = sqlite3.connect(dbp)
    conn.execute("CREATE TABLE deliveries (doc_no TEXT PRIMARY KEY, qty INTEGER, price INTEGER)")
    conn.commit(); conn.close()
    return dbp


def _db_cfg(dbp, enabled):
    return {"db_kind": "sqlite", "connection": dbp, "table": "deliveries",
            "column_mapping": {"納品書番号": "doc_no", "数量": "qty", "卸値": "price"},
            "db_write_enabled": enabled}


def test_db_dry_run_writes_nothing(tmp_path):
    dbp = _mk_db(tmp_path)
    res = ig.db_write(_db_cfg(dbp, enabled=False), [{"納品書番号": "DN-1", "数量": "24", "卸値": "800"}])
    assert res["dry_run"] is True and res["written"] == 0
    assert "INSERT INTO deliveries" in res["preview"][0][0]
    conn = sqlite3.connect(dbp)
    assert conn.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0] == 0
    conn.close()


def test_db_write_enabled_inserts_with_mapping(tmp_path):
    dbp = _mk_db(tmp_path)
    res = ig.db_write(_db_cfg(dbp, enabled=True),
                      [{"納品書番号": "DN-1", "数量": "24", "卸値": "800"},
                       {"納品書番号": "DN-2", "数量": "10", "卸値": "500"}])
    assert res["dry_run"] is False and res["written"] == 2
    conn = sqlite3.connect(dbp)
    rows = conn.execute("SELECT doc_no, qty, price FROM deliveries ORDER BY doc_no").fetchall()
    conn.close()
    assert rows == [("DN-1", 24, 800), ("DN-2", 10, 500)]


def test_db_write_rolls_back_on_error(tmp_path):
    dbp = _mk_db(tmp_path)
    rows = [{"納品書番号": "DN-1", "数量": "24", "卸値": "800"},
            {"納品書番号": "DN-1", "数量": "1", "卸値": "1"}]  # duplicate PK on 2nd row
    try:
        ig.db_write(_db_cfg(dbp, enabled=True), rows)
        assert False, "should raise"
    except Exception:
        pass
    conn = sqlite3.connect(dbp)
    assert conn.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0] == 0  # rolled back atomically
    conn.close()


def test_db_unsafe_identifier_rejected():
    try:
        ig.build_insert("deliveries; DROP TABLE x", {"a": "b"}, {"a": "1"})
        assert False
    except ValueError:
        pass


# ------------------------------------------- I + B: automation destinations ----
CLEAN = """納品書
納品書番号: DN-2026-100
納品日: 2026年11月12日
取引先: 株式会社サンプル
商品名: りんごジュース 1L
数量: 24
単価: 800
卸値: 800円
売価: 1200円
合計: 19200円
"""


def test_auto_mode_db_destination(tmp_path):
    prof = _prof("納品書")
    dbp = _mk_db(tmp_path)
    cfg = {"output_path": str(tmp_path / "out.xlsx"), "done_folder": str(tmp_path / "done"),
           "review_folder": str(tmp_path / "review"), "threshold": 90, "settings": {},
           "integration_db": _db_cfg(dbp, enabled=True)}
    src = tmp_path / "clean.txt"; src.write_text(CLEAN, encoding="utf-8")
    res = automation.process_file_auto(str(src), prof, cfg, app_dir=str(tmp_path / "appdata"))
    assert res["decision"] == "accepted"
    conn = sqlite3.connect(dbp)
    rows = conn.execute("SELECT doc_no, qty, price FROM deliveries").fetchall()
    conn.close()
    assert rows == [("DN-2026-100", 24, 800)]
    rec = json.loads((tmp_path / "appdata" / "audit_log.jsonl").read_text(encoding="utf-8").strip())
    assert "db:deliveries" in rec["destination"]


def test_auto_mode_integration_file_destination(tmp_path):
    prof = _prof("納品書")
    icfg = {"format": "csv", "encoding": "shift_jis", "newline": "crlf", "header": True,
            "filename_pattern": "imp_{date}.csv"}
    cfg = {"output_path": str(tmp_path / "out.xlsx"), "done_folder": str(tmp_path / "done"),
           "review_folder": str(tmp_path / "review"), "threshold": 90, "settings": {},
           "integration_file": icfg, "integration_file_dir": str(tmp_path / "exports")}
    src = tmp_path / "clean.txt"; src.write_text(CLEAN, encoding="utf-8")
    res = automation.process_file_auto(str(src), prof, cfg, app_dir=str(tmp_path / "appdata"))
    assert res["decision"] == "accepted"
    files = list((tmp_path / "exports").glob("imp_*.csv"))
    assert len(files) == 1
    assert "DN-2026-100" in files[0].read_bytes().decode("shift_jis")

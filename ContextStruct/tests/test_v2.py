# -*- coding: utf-8 -*-
"""ContextStruct v2 tests: preprocessing, ensemble agreement/verification,
master matching, complete automation, learning, 7B model registry.
All engine tests use FAKE engines / mock runners — no real OCR binary and
no multi-GB model download is needed."""
import sys, os, json, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PIL import Image, ImageDraw
from context_core import (preset_profiles, FieldResult, rows_to_dicts)
import preprocess as pp
import ensemble
import learning
import automation
import vlm_local


def _prof(part):
    for p in preset_profiles():
        if part in p.name:
            return p
    raise AssertionError(part)


def _row(prof, spec):
    """spec: {col: (value, conf)} -> FieldResult row"""
    return {f.target_column: FieldResult(spec.get(f.target_column, ("", 0))[0],
                                         spec.get(f.target_column, ("", 0))[1], "fake", "")
            for f in prof.fields}


# ------------------------------------------------------------ A1 preprocess
def _pattern(angle=0.0, size=(800, 600)):
    img = Image.new("RGB", size, (255, 255, 255))
    d = ImageDraw.Draw(img)
    for y in range(80, size[1] - 40, 48):
        for x in range(60, size[0] - 60, 26):
            d.rectangle([x, y, x + 16, y + 10], fill=(0, 0, 0))
    if angle:
        img = img.rotate(angle, resample=Image.BICUBIC, fillcolor=(255, 255, 255))
    return img


def test_preprocess_variants_sizes_modes():
    out = pp.preprocess_image(_pattern(0), upscale=True)
    assert set(out.keys()) == {"original", "enhanced", "binarized"}
    for im in out.values():
        assert im.size == (1600, 1200) and im.mode == "RGB"
    out2 = pp.preprocess_image(_pattern(0), upscale=False)
    assert out2["original"].size == (800, 600)


def test_preprocess_low_contrast_enhanced_differs():
    faint = Image.new("RGB", (200, 100), (212, 212, 212))
    d = ImageDraw.Draw(faint)
    d.rectangle([20, 40, 180, 60], fill=(188, 188, 188))
    en = pp.enhance_image(faint)
    assert en.size == faint.size
    spread_before = max(faint.convert("L").getdata()) - min(faint.convert("L").getdata())
    spread_after = max(en.convert("L").getdata()) - min(en.convert("L").getdata())
    assert spread_after > spread_before  # CLAHE actually stretched the faint contrast


def test_deskew_reduces_measured_skew():
    for ang in (4.0, -3.0):
        img = _pattern(ang)
        before = abs(pp.estimate_skew(img))
        assert before >= abs(ang) - 1.0
        after = abs(pp.estimate_skew(pp.deskew_image(img)))
        assert after < before and after <= 1.0


def test_preprocess_to_files(tmp_path):
    src = tmp_path / "scan.png"
    _pattern(2.0).save(src)
    paths = pp.preprocess_to_files(str(src), out_dir=str(tmp_path / "out"))
    assert set(paths) == {"original", "enhanced", "binarized"}
    for p in paths.values():
        assert os.path.isfile(p)
        assert Image.open(p).size == (1600, 1200)


# ------------------------------------------------------- A2 ensemble merger
def test_agreement_boost_two_engines():
    prof = _prof("納品書")
    spec = {"卸値": ("800", 90), "売価": ("1200", 88), "数量": ("24", 95)}
    engines = {"eng_a": [_row(prof, spec)], "eng_b": [_row(prof, spec)]}
    rows, report = ensemble.merge_engine_rows(engines, prof)
    assert 97 <= rows[0]["卸値"].confidence <= 99
    assert rows[0]["卸値"].value == "800"
    assert report["fields"][(0, "卸値")]["agreed"] is True
    assert report["disputed"] == []


def test_single_engine_keeps_confidence():
    prof = _prof("納品書")
    engines = {"only": [_row(prof, {"卸値": ("800", 72)})]}
    rows, report = ensemble.merge_engine_rows(engines, prof)
    assert rows[0]["卸値"].confidence == 72
    assert report["fields"][(0, "卸値")]["agreed"] is False


def test_disagreement_caps_and_flags():
    prof = _prof("納品書")
    engines = {"a": [_row(prof, {"卸値": ("800", 95)})],
               "b": [_row(prof, {"卸値": ("850", 95)})],
               "c": [_row(prof, {"卸値": ("800", 95)})]}
    rows, report = ensemble.merge_engine_rows(engines, prof)
    assert rows[0]["卸値"].value == "800"          # most supported wins
    assert rows[0]["卸値"].confidence <= ensemble.DISAGREE_CAP
    assert (0, "卸値") in report["disputed"]


def test_agreement_after_normalization():
    prof = _prof("納品書")
    engines = {"a": [_row(prof, {"卸値": ("¥800円", 90)})],
               "b": [_row(prof, {"卸値": ("800", 90)})]}
    rows, report = ensemble.merge_engine_rows(engines, prof)
    assert rows[0]["卸値"].value in ("800", "¥800円")
    assert rows[0]["卸値"].confidence >= 97  # normalized values agree


# ------------------------------------------------- A3 arithmetic validation
def _delivery_row(qty="24", unit="800", total="19200"):
    prof = _prof("納品書")
    return prof, _row(prof, {"数量": (qty, 95), "単価": (unit, 95), "合計": (total, 95),
                             "卸値": ("800", 95), "売価": ("1200", 95)})


def test_arithmetic_pass_keeps_confidence():
    prof, row = _delivery_row()
    res = ensemble.arithmetic_validation([row], prof)
    assert res["passed"] is True
    assert row["合計"].confidence == 95


def test_arithmetic_fail_lowers_confidence():
    prof, row = _delivery_row(total="99999")
    res = ensemble.arithmetic_validation([row], prof)
    assert res["passed"] is False
    assert row["合計"].confidence < 95
    assert "arith_fail" in row["合計"].reason
    assert (0, "合計") in res["failed_fields"]


def test_tax_pattern_check():
    prof = _prof("請求書")
    good = _row(prof, {"小計": ("50000", 95), "消費税": ("5000", 95), "請求金額": ("55000", 95)})
    assert ensemble.arithmetic_validation([good], prof)["passed"] is True
    bad = _row(prof, {"小計": ("50000", 95), "消費税": ("1234", 95), "請求金額": ("55000", 95)})
    res = ensemble.arithmetic_validation([bad], prof)
    assert res["passed"] is False
    assert bad["消費税"].confidence < 95


# ------------------------------------------- A3b targeted re-read on dispute
def test_targeted_reread_invoked_on_disagreement(tmp_path):
    prof = _prof("納品書")
    img = tmp_path / "doc.png"
    Image.new("RGB", (32, 32), "white").save(img)
    calls = []
    def fake_reread_runner(prompt, image_path):
        calls.append((prompt, image_path))
        assert "卸値" in prompt  # field-specific question
        return '{"卸値": "800"}'
    engines = {"a": [_row(prof, {"卸値": ("850", 90)})], "b": [_row(prof, {"卸値": ("800", 90)})]}
    rows, report = ensemble.merge_engine_rows(engines, prof)
    assert (0, "卸値") in report["disputed"]
    done = ensemble.verify_and_reread(rows, prof, str(img), report["disputed"], runner=fake_reread_runner)
    assert done == [(0, "卸値")] and len(calls) == 1
    assert rows[0]["卸値"].value == "800"
    assert rows[0]["卸値"].confidence >= 85  # replaced by the targeted re-read value


def test_reread_agreement_boosts_existing():
    prof = _prof("納品書")
    rows = [_row(prof, {"卸値": ("800", 60)})]
    def runner(prompt, image_path):
        return '{"卸値": "800"}'
    ensemble.verify_and_reread(rows, prof, "x.png", [(0, "卸値")], runner=runner)
    assert rows[0]["卸値"].confidence >= 96
    assert "verify_reread agreed" in rows[0]["卸値"].reason


# ------------------------------------------------------------ A3c master CSV
def test_master_snap_and_boost(tmp_path):
    prof = _prof("納品書")
    mp = tmp_path / "master.csv"
    with open(mp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["code", "name"]); w.writerow(["AJ-1L", "りんごジュース 1L"])
    master = ensemble.load_master(str(mp))
    assert master == [{"code": "AJ-1L", "name": "りんごジュース 1L"}]
    rows = [_row(prof, {"商品名": ("りんごジュース 1L（仮）", 70)})]
    # fuzzy: close but not exact spelling still snaps when similar enough OR stays
    n = ensemble.master_match(rows, prof, master)
    rows2 = [_row(prof, {"商品名": ("りんごジュース 1L", 70)})]
    n2 = ensemble.master_match(rows2, prof, master)
    assert n2 == 1
    assert rows2[0]["商品名"].value == "りんごジュース 1L"
    assert rows2[0]["商品名"].confidence > 70
    assert "master matched" in rows2[0]["商品名"].reason


def test_master_first_two_columns_fallback(tmp_path):
    mp = tmp_path / "m2.csv"
    with open(mp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["X-9", "株式会社サンプル"]); w.writerow(["Y-1", "株式会社テスト"])
    entries = ensemble.load_master(str(mp))
    assert {"code": "X-9", "name": "株式会社サンプル"} in entries


# --------------------------------------------------------- C: 7B registry
def test_model_registry_7b_verified_filenames():
    spec = vlm_local.model_spec("7b")
    assert spec["model_file"] == "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"
    assert spec["mmproj_file"] == "mmproj-Qwen2.5-VL-7B-Instruct-Q8_0.gguf"
    assert spec["model_bytes"] == 4683072032 and spec["mmproj_bytes"] == 853119712
    total_gb = (spec["model_bytes"] + spec["mmproj_bytes"]) / 1e9
    assert 5.0 <= total_gb <= 6.0
    spec3 = vlm_local.model_spec("3b")
    assert spec3["model_bytes"] == 1929901056 and spec3["mmproj_bytes"] == 844757728


def test_model_status_per_model(tmp_path):
    d = str(tmp_path)
    st = vlm_local.model_status(d, model_key="7b", min_model_bytes=1, min_mmproj_bytes=1)
    assert st["complete"] is False and st["model_key"] == "7b"
    assert set(st["missing"]) == {vlm_local.MODEL7_FILE, vlm_local.MMPROJ7_FILE}


def test_prompt_variants_differ_and_few_shot():
    prof = _prof("納品書")
    p0 = vlm_local.build_vlm_prompt(prof, variant=0)
    p1 = vlm_local.build_vlm_prompt(prof, variant=1)
    assert p0 != p1
    assert "handwriting" in p0.lower() and "handwriting" in p1.lower()
    fs = [{"field": "卸値", "original": "850", "corrected": "800", "source_snippet": "卸値: 800"}]
    pf = vlm_local.build_vlm_prompt(prof, few_shot=fs)
    assert "850" in pf and "800" in pf and "卸値" in pf


def test_self_consistency_two_phrasings_agree_boost():
    """C2: the same VLM read twice with two phrasings — the ensemble merger
    boosts fields both phrasings agree on."""
    prof = _prof("納品書")
    seen_prompts = []
    def runner(prompt, image_path):
        seen_prompts.append(prompt)
        return '{"fields": {"卸値": "800", "売価": "1200"}, "items": []}'
    engines = {}
    for variant, name in ((0, "vlm_p1"), (1, "vlm_p2")):
        engines[name] = vlm_local.run_local_vlm("dummy.png", prof, runner=runner, prompt_variant=variant)
    assert len(seen_prompts) == 2 and seen_prompts[0] != seen_prompts[1]
    rows, report = ensemble.merge_engine_rows(engines, prof)
    assert rows[0]["卸値"].confidence >= 97
    assert report["disputed"] == []


# ------------------------------------------------------- E: learning layer
def test_correction_saved_on_confirm(tmp_path):
    d = str(tmp_path)
    learning.save_correction("納品書 Delivery Note", "卸値", "850", "800", "卸値: 800", base_dir=d)
    recs = learning.load_corrections(base_dir=d)
    assert len(recs) == 1 and recs[0]["corrected"] == "800" and recs[0]["field"] == "卸値"
    recent = learning.recent_corrections("納品書 Delivery Note", 5, base_dir=d)
    assert len(recent) == 1


def test_alias_learned_from_snippet():
    prof = _prof("納品書")
    f = next(x for x in prof.fields if x.target_column == "取引先")
    assert "お届け先" not in f.keywords
    src = "納品書\nお届け先: 株式会社サンプル\n数量: 24\n"
    learned = learning.learn_alias(prof, "取引先", "株式会社サンプル", src)
    assert learned == "お届け先"
    assert "お届け先" in f.keyword_list()
    # already-known keyword is not learned twice
    assert learning.learn_alias(prof, "取引先", "株式会社サンプル", src) is None


def test_few_shot_prompt_contains_prior_correction(tmp_path):
    d = str(tmp_path)
    learning.save_correction("納品書 Delivery Note", "卸値", "850", "800", "卸値: 800円", base_dir=d)
    few = learning.recent_corrections("納品書 Delivery Note", 5, base_dir=d)
    prof = _prof("納品書")
    prompt = vlm_local.build_vlm_prompt(prof, few_shot=few)
    assert "850" in prompt and '"800"' in prompt


def test_vendor_profile_memory_roundtrip(tmp_path):
    d = str(tmp_path)
    assert learning.profile_for_vendor("株式会社サンプル", base_dir=d) is None
    learning.remember_vendor_profile("株式会社サンプル", "請求書 Invoice", base_dir=d)
    assert learning.profile_for_vendor("株式会社サンプル", base_dir=d) == "請求書 Invoice"


def test_detect_vendor():
    prof = _prof("納品書")
    rows = [_row(prof, {"取引先": ("株式会社サンプル", 90)})]
    assert learning.detect_vendor(rows, prof) == "株式会社サンプル"


# ------------------------------------------------- B: complete automation
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
LOWQ = "納品書\nよく読めないメモ\n"


def _cfg(tmp_path, out_name="out.xlsx"):
    return {"output_path": str(tmp_path / out_name),
            "done_folder": str(tmp_path / "done"),
            "review_folder": str(tmp_path / "review"),
            "threshold": 90, "settings": {}}


def test_auto_accept_clean_txt(tmp_path):
    prof = _prof("納品書")
    src = tmp_path / "clean.txt"; src.write_text(CLEAN, encoding="utf-8")
    res = automation.process_file_auto(str(src), prof, _cfg(tmp_path), app_dir=str(tmp_path / "appdata"))
    assert res["decision"] == "accepted", res["low"]
    assert not src.exists()
    assert os.path.isfile(os.path.join(str(tmp_path), "done", "clean.txt"))
    from openpyxl import load_workbook
    wb = load_workbook(str(tmp_path / "out.xlsx")); ws = wb.active
    vals = [[c.value for c in r] for r in ws.iter_rows()]
    assert vals[0] == [f.target_column for f in prof.fields]
    assert "DN-2026-100" in vals[1] and "800" in vals[1]
    audit = (tmp_path / "appdata" / "audit_log.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(audit) == 1
    rec = json.loads(audit[0])
    assert rec["decision"] == "accepted" and rec["source_file"] == "clean.txt"
    assert rec["values"][0]["卸値"] == "800" and rec["arithmetic_passed"] is True


def test_auto_review_low_quality(tmp_path):
    prof = _prof("納品書")
    src = tmp_path / "bad.txt"; src.write_text(LOWQ, encoding="utf-8")
    res = automation.process_file_auto(str(src), prof, _cfg(tmp_path), app_dir=str(tmp_path / "appdata"))
    assert res["decision"] == "review"
    assert os.path.isfile(os.path.join(str(tmp_path), "review", "bad.txt"))
    assert not os.path.exists(str(tmp_path / "out.xlsx"))  # nothing appended
    rec = json.loads((tmp_path / "appdata" / "audit_log.jsonl").read_text(encoding="utf-8").strip())
    assert rec["decision"] == "review"


def test_auto_csv_output_mode(tmp_path):
    prof = _prof("納品書")
    src = tmp_path / "c.txt"; src.write_text(CLEAN, encoding="utf-8")
    res = automation.process_file_auto(str(src), prof, _cfg(tmp_path, "out.csv"), app_dir=str(tmp_path / "appdata"))
    assert res["decision"] == "accepted"
    lines = (tmp_path / "out.csv").read_text(encoding="utf-8-sig").strip().splitlines()
    assert len(lines) == 2 and "DN-2026-100" in lines[1]


def test_scan_watch_folder(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "b.pdf").write_bytes(b"%PDF")
    (tmp_path / "c.exe").write_bytes(b"no")
    found = automation.scan_watch_folder(str(tmp_path))
    assert [os.path.basename(f) for f in found] == ["a.txt", "b.pdf"]


def test_pipeline_with_fake_vlm_engine():
    """run_pipeline end-to-end with a mock VLM runner as the only engine."""
    prof = _prof("納品書")
    def runner(prompt, image_path):
        return '{"fields": {"納品書番号": "DN-1", "数量": "24", "単価": "800", "合計": "19200"}, "items": []}'
    rows, info = ensemble.run_pipeline(prof, text="", image_path="dummy.png",
                                       settings={}, use_vlm=True, vlm_runner=runner, verify=False)
    assert "vlm_p1" in info["engines"] and "vlm_p2" in info["engines"]
    d = rows_to_dicts(rows, prof)[0]
    assert d["納品書番号"] == "DN-1" and d["合計"] == "19200"
    assert rows[0]["合計"].confidence >= 97  # two phrasings agreed

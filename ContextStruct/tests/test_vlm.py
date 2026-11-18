# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from context_core import preset_profiles, rows_to_dicts
import vlm_local
from vlm_local import (build_vlm_prompt, parse_vlm_json, vlm_data_to_rows,
                       model_status, models_dir, run_local_vlm, prepare_vlm_image,
                       MODEL_FILE, MMPROJ_FILE)

def _prof(name_part):
    for p in preset_profiles():
        if name_part in p.name: return p
    raise AssertionError(name_part)

# --- prompt generation ---
def test_prompt_includes_fields_and_wholesale_retail_distinction():
    prof = _prof("納品書")
    prompt = build_vlm_prompt(prof)
    for f in prof.fields:
        assert f.target_column in prompt
    assert "卸値" in prompt and "売価" in prompt
    assert "DIFFERENT" in prompt  # explicit distinction instruction

def test_prompt_image_understanding_requirements():
    prof = _prof("納品書")
    prompt = build_vlm_prompt(prof)
    low = prompt.lower()
    assert "image" in low and "not ocr" in low          # image itself, not OCR text
    assert "table structure" in low and "rows and columns" in low
    assert "spatial layout" in low and "position" in low  # heading/value positions
    assert "items" in low                                 # line items row by row
    assert "do not guess" in low                          # never fill by guessing
    assert "tilted" in low and "handwritten" in low       # imperfect scans

# --- tolerant JSON parsing ---
def test_parse_vlm_json_fenced_and_noisy():
    raw = 'Here is the result:\n```json\n{"卸値": "800", "売価": "1,200"}\n```\nHope this helps!'
    d = parse_vlm_json(raw)
    assert d["卸値"] == "800" and d["売価"] == "1,200"
    assert parse_vlm_json('{"a": 1,}') == {"a": 1}       # trailing comma tolerated
    assert parse_vlm_json('no json here') == {}

# --- model management ---
def test_model_status_missing_and_present(tmp_path):
    d = str(tmp_path / "models"); os.makedirs(d)
    st = model_status(d, min_model_bytes=1, min_mmproj_bytes=1)
    assert st["complete"] is False
    assert set(st["missing"]) == {MODEL_FILE, MMPROJ_FILE}
    with open(os.path.join(d, MODEL_FILE), "wb") as f: f.write(b"x" * 10)
    st = model_status(d, min_model_bytes=1, min_mmproj_bytes=1)
    assert st["complete"] is False and st["missing"] == [MMPROJ_FILE]
    with open(os.path.join(d, MMPROJ_FILE), "wb") as f: f.write(b"y" * 10)
    st = model_status(d, min_model_bytes=1, min_mmproj_bytes=1)
    assert st["complete"] is True and st["missing"] == []
    # real thresholds reject tiny dummy files
    st2 = model_status(d)
    assert st2["complete"] is False

def test_models_dir_path():
    d = models_dir()
    assert os.path.basename(d) == "models"
    assert "contextstruct" in d.lower()

def test_runtime_binary_bundled():
    b = vlm_local.find_runtime_binary()
    assert b is not None and os.path.basename(b).startswith("llama-mtmd-cli")

# --- mock runner: the VLM receives an IMAGE PATH, not text ---
def test_mock_runner_receives_image_path(tmp_path):
    from PIL import Image
    img = tmp_path / "scan.png"; Image.new("RGB", (64, 64), (255, 255, 255)).save(img)
    seen = {}
    def runner(prompt, image_path):
        seen["prompt"] = prompt; seen["image_path"] = image_path
        return '{"fields": {"卸値": "800", "売価": "1200"}, "items": []}'
    prof = _prof("納品書")
    rows = run_local_vlm(str(img), prof, runner=runner)
    # called with the image file path itself
    assert seen["image_path"] == str(img)
    assert os.path.splitext(seen["image_path"])[1] == ".png"
    assert "納品書番号: DN" not in seen["image_path"]  # not document text
    d = rows_to_dicts(rows, prof)[0]
    assert d["卸値"] == "800" and d["売価"] == "1200"
    assert rows[0]["卸値"].confidence >= 80
    assert rows[0]["合計"].confidence == 0  # missing stays empty / 0

def test_mock_runner_line_items_rows():
    def runner(prompt, image_path):
        return ('```json {"fields": {"取引先": "株式会社X", "卸値": "800", "売価": "1200"}, '
                '"items": [{"商品名": "りんご", "数量": "10"}, {"商品名": "みかん", "数量": "20"}]} ```')
    prof = _prof("納品書")
    rows = run_local_vlm("dummy.png", prof, runner=runner)
    dicts = rows_to_dicts(rows, prof)
    assert len(dicts) == 2
    assert dicts[0]["商品名"] == "りんご" and dicts[1]["商品名"] == "みかん"
    assert dicts[0]["卸値"] == "800" and dicts[1]["売価"] == "1200"  # doc fields fill every row

def test_pdf_to_image_to_vlm_mock(tmp_path):
    import fitz
    pdf = str(tmp_path / "scan.pdf")
    doc = fitz.open(); page = doc.new_page(); page.insert_text((72, 72), "FAX delivery note (scanned)"); doc.save(pdf); doc.close()
    img_path = prepare_vlm_image(pdf, dpi=150)
    assert img_path and os.path.isfile(img_path) and img_path.endswith(".png")
    seen = {}
    def runner(prompt, image_path):
        seen["image_path"] = image_path
        return '{"請求書番号": "INV-9", "請求金額": "55000"}' if False else '{"fields": {"納品書番号": "DN-7", "合計": "19200"}, "items": []}'
    prof = _prof("納品書")
    rows = run_local_vlm(img_path, prof, runner=runner)
    assert seen["image_path"] == img_path and seen["image_path"].endswith(".png")
    d = rows_to_dicts(rows, prof)[0]
    assert d["納品書番号"] == "DN-7" and d["合計"] == "19200"

def test_prepare_vlm_image_passthrough_and_text_none(tmp_path):
    p = tmp_path / "a.jpg"; p.write_bytes(b"\xff\xd8")
    assert prepare_vlm_image(str(p)) == str(p)
    t = tmp_path / "a.txt"; t.write_text("hi")
    assert prepare_vlm_image(str(t)) is None
    assert prepare_vlm_image(None) is None

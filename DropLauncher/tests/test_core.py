# -*- coding: utf-8 -*-
import sys, subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core
import pytest

@pytest.fixture()
def settings(tmp_path):
    s = dict(core.DEFAULT_SETTINGS)
    s["output_base"] = str(tmp_path / "out")
    s["project"] = "作業"
    return s

def test_image(settings, tmp_path):
    from PIL import Image
    src = tmp_path / "big.png"
    Image.new("RGB", (2400, 1200), (200, 50, 50)).save(src)
    dest = core.convert_image(src, settings)
    assert dest.exists() and dest.suffix == ".jpg"
    im = Image.open(dest)
    assert im.width == 1200
    # small target attempt
    settings["image_target_kb"] = 30
    noisy = tmp_path / "noise.png"
    import random; random.seed(1)
    im2 = Image.new("RGB", (800, 800))
    im2.putdata([(random.randint(0,255), random.randint(0,255), random.randint(0,255)) for _ in range(800*800)])
    im2.save(noisy)
    d2 = core.convert_image(noisy, settings)
    assert d2.exists() and d2.stat().st_size > 0

def _make_pdf(path, texts):
    import fitz
    doc = fitz.open()
    for t in texts:
        page = doc.new_page()
        page.insert_text((72, 72), t)
    doc.save(path); doc.close()

def test_pdf_merge_split_text(settings, tmp_path):
    a, b = tmp_path/"a.pdf", tmp_path/"b.pdf"
    _make_pdf(a, ["Hello A1", "Hello A2"]); _make_pdf(b, ["Hello B1"])
    merged = core.pdf_merge([a, b], settings)
    import fitz; doc = fitz.open(merged); assert doc.page_count == 3; doc.close()
    pages = core.pdf_split(a, settings)
    assert len(pages) == 2 and all(p.exists() for p in pages)
    txt = core.pdf_extract_text(a, settings)
    assert "Hello A1" in txt.read_text(encoding="utf-8")

def test_sort_rename_undo(settings, tmp_path):
    f1 = tmp_path/"x.txt"; f1.write_text("1")
    f2 = tmp_path/"y.txt"; f2.write_text("2")
    ops = core.sort_rename_files([f1, f2], settings)
    assert len(ops) == 2
    names = sorted(Path(o["dst"]).name for o in ops)
    assert names[0].endswith("_001.txt") and names[1].endswith("_002.txt")
    assert not f1.exists()
    n = core.undo_last(settings)
    assert n == 2 and f1.exists() and f2.exists()

def _make_xlsx(path):
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "日報"
    ws.append(["日付", "項目", "金額", "状態"])
    ws["A1"].font = Font(bold=True, color="FF0000")
    ws["A1"].fill = PatternFill("solid", fgColor="FFFF00")
    ws.append(["2026-11-12", "A", 100, "完了"])
    ws.append(["2026-11-12", "B", 250, "完了"])
    ws.append(["2026-11-12", "C", 50, "作業中"])
    ws.column_dimensions["A"].width = 30
    wb.save(path)

def test_transcribe_styled_and_pdf(settings, tmp_path):
    src = tmp_path/"in.xlsx"; _make_xlsx(src)
    outs = core.transcribe_file(src, settings)
    names = [o.name for o in outs]
    assert any("書式コピー" in n for n in names)
    import openpyxl
    copied = [o for o in outs if "書式コピー" in o.name][0]
    wb = openpyxl.load_workbook(copied); ws = wb.active
    assert ws["A1"].fill.fgColor.rgb.endswith("FFFF00")
    assert ws["A1"].font.bold
    # PDF -> outputs
    p = tmp_path/"t.pdf"; _make_pdf(p, ["Transcribe Me"])
    outs2 = core.transcribe_file(p, settings)
    assert any(o.suffix == ".xlsx" for o in outs2) and any(o.suffix == ".txt" for o in outs2)

def test_report(settings, tmp_path):
    src = tmp_path/"report.xlsx"; _make_xlsx(src)
    r = core.aggregate_report(src, settings)
    assert r["rows"] == 3 and r["done"] == 2 and r["sums"]["金額"] == 400
    assert "日報集計" in r["report_text"] and Path(r["txt"]).exists() and Path(r["summary"]).exists()

def test_archive(settings, tmp_path):
    f = tmp_path/"a.txt"; f.write_text("hello")
    z = core.archive_zip([f], settings)
    assert z.exists() and z.suffix == ".zip"
    dest = core.archive_extract(z, settings)
    assert (Path(dest)/"a.txt").exists()

def test_excel_html_csv(settings, tmp_path):
    src = tmp_path/"book.xlsx"; _make_xlsx(src)
    h = core.xlsx_to_html(src, settings)
    content = h.read_text(encoding="utf-8")
    assert "background-color" in content or "font-weight:bold" in content
    csvs = core.xlsx_to_csv(src, settings)
    assert csvs and "金額" in csvs[0].read_text(encoding="utf-8-sig")
    out, engine = core.convert_to_pdf(src, settings)
    assert Path(out).exists()
    # On this Linux VM without LibreOffice, engine must be the HTML fallback
    print("engine:", engine)

def test_video(settings, tmp_path):
    ffmpeg = core.find_ffmpeg(settings)
    assert ffmpeg, "ffmpeg not found"
    src = tmp_path/"src.mp4"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:v", "libx264", "-c:a", "aac", "-shortest", str(src)],
                   check=True, capture_output=True)
    assert src.exists() and src.stat().st_size > 0
    mp4 = core.convert_video(src, settings, preset="mp4"); assert mp4.exists() and mp4.stat().st_size > 0
    comp = core.convert_video(src, settings, preset="compress"); assert comp.exists() and comp.stat().st_size > 0
    mp3 = core.convert_video(src, settings, preset="mp3"); assert mp3.exists() and mp3.stat().st_size > 0 and mp3.suffix == ".mp3"
    gif = core.convert_video(src, settings, preset="gif"); assert gif.exists() and gif.stat().st_size > 0

def test_spaces_and_japanese_folder(settings, tmp_path):
    work = tmp_path / "空白 と 日本語フォルダ"
    work.mkdir()
    settings["output_base"] = str(work / "出力 先")
    from PIL import Image
    img = work / " MiXeD アクセント é.png"
    Image.new("RGB", (1600, 900), (10, 20, 30)).save(img)
    dest = core.convert_image(img, settings)
    assert dest.exists()
    f = work / "メモ テキスト.txt"
    f.write_text("abc")
    ops = core.sort_rename_files([f], settings)
    assert ops and Path(ops[0]["dst"]).exists()
    z = core.archive_zip([Path(ops[0]["dst"])], settings)
    assert z.exists()
    ex = core.archive_extract(z, settings)
    assert any(Path(ex).rglob("*.txt"))

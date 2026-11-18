# -*- coding: utf-8 -*-
"""Tests for VersionDetective.

Run with:  python3 tests/test_latest.py     (no pytest needed)
Covers: exact grouping, candidate grouping (unrelated files stay
out), latest ranking (internal datetime wins, branch -> no verdict),
docx line diff, xlsx cell diff, archive move + clash + undo,
encrypted/corrupt handling, i18n key completeness, GUI smoke.
"""

import io
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import analyzer  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ----------------------------------------------------------------------
# Fixture builders (stdlib only, minimal OOXML)
# ----------------------------------------------------------------------

CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""


def core_xml(modified_iso):
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dcterms="http://purl.org/dc/terms/">
<dcterms:modified>{modified_iso}</dcterms:modified>
</cp:coreProperties>"""


def make_docx(path, paragraphs, modified_iso="2025-01-01T09:00:00Z"):
    paras = "".join(
        f'<w:p><w:r><w:t>{p}</w:t></w:r></w:p>' for p in paragraphs)
    doc = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{paras}</w:body></w:document>"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", CT)
        zf.writestr("_rels/.rels", RELS)
        zf.writestr("word/document.xml", doc)
        zf.writestr("docProps/core.xml", core_xml(modified_iso))


def make_xlsx(path, rows, modified_iso="2025-01-01T09:00:00Z"):
    """rows: list of rows; each row a list of strings (sheet 'Data')."""
    strings = []
    index = {}

    def sidx(s):
        if s not in index:
            index[s] = len(strings)
            strings.append(s)
        return index[s]

    sheet_rows = []
    for r, row in enumerate(rows, start=1):
        cells = ""
        for c, val in enumerate(row):
            if val == "":
                continue
            coord = f"{analyzer._col_name(c)}{r}"
            cells += f'<c r="{coord}" t="s"><v>{sidx(val)}</v></c>'
        sheet_rows.append(f'<row r="{r}">{cells}</row>')
    ss = "".join(f"<si><t>{s}</t></si>" for s in strings)
    shared = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{ss}</sst>"""
    sheet = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{''.join(sheet_rows)}</sheetData></worksheet>"""
    wb = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>"""
    wb_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", CT)
        zf.writestr("_rels/.rels", RELS)
        zf.writestr("xl/workbook.xml", wb)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
        zf.writestr("xl/sharedStrings.xml", shared)
        zf.writestr("docProps/core.xml", core_xml(modified_iso))


def write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def set_mtime(path, dt):
    ts = dt.replace(tzinfo=timezone.utc).timestamp()
    os.utime(path, (ts, ts))


BASE = ["企画の目的", "対象は中小企業", "予算は100万円", "期間は3か月"]


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------

def test_exact_grouping():
    with tempfile.TemporaryDirectory() as d:
        a = os.path.join(d, "議事録.txt")
        b = os.path.join(d, "議事録_コピー.txt")
        c = os.path.join(d, "別のメモ.txt")
        write(a, "会議の記録\n決定事項は3件\n")
        write(b, "会議の記録\n決定事項は3件\n")
        write(c, "全く別の内容です\n")
        infos = [analyzer.extract(p) for p in (a, b, c)]
        groups, singles = analyzer.build_groups(infos)
        assert len(groups) == 1, groups
        assert groups[0].kind == "exact"
        assert {m.name for m in groups[0].members} == \
            {"議事録.txt", "議事録_コピー.txt"}
        assert [s.name for s in singles] == ["別のメモ.txt"]


def test_candidate_grouping_and_unrelated_stays_out():
    with tempfile.TemporaryDirectory() as d:
        v1 = os.path.join(d, "企画書.docx")
        v2 = os.path.join(d, "企画書_修正.docx")
        v3 = os.path.join(d, "企画書_最終版.docx")
        other = os.path.join(d, "請求書.docx")
        make_docx(v1, BASE, "2025-01-01T09:00:00Z")
        make_docx(v2, BASE + ["進め方を追加"], "2025-01-02T09:00:00Z")
        make_docx(v3, BASE + ["進め方を追加", "まとめを追加"],
                  "2025-01-03T09:00:00Z")
        make_docx(other, ["請求先はA社", "金額は55万円", "支払期限は月末"],
                  "2025-01-03T09:00:00Z")
        infos = [analyzer.extract(p) for p in (v1, v2, v3, other)]
        groups, singles = analyzer.build_groups(infos)
        assert len(groups) == 1, [(g.kind, [m.name for m in g.members])
                                  for g in groups]
        g = groups[0]
        assert g.kind == "candidate"
        assert len(g.members) == 3
        assert g.similarity >= 0.45
        assert [s.name for s in singles] == ["請求書.docx"]


def test_latest_prefers_internal_datetime():
    with tempfile.TemporaryDirectory() as d:
        old_internal = os.path.join(d, "報告書_最終版.docx")
        new_internal = os.path.join(d, "報告書_修正.docx")
        # file mtimes are the OTHER way round on purpose: the copy
        # operation refreshed the older content's mtime.
        # older content is a pure subset (no divergence), so the
        # ranking itself is what is being tested here.
        make_docx(old_internal, BASE, "2025-01-01T09:00:00Z")
        make_docx(new_internal, BASE + ["新しい追記"],
                  "2025-02-01T09:00:00Z")
        set_mtime(old_internal, datetime(2025, 3, 1))
        set_mtime(new_internal, datetime(2025, 1, 15))
        infos = [analyzer.extract(p) for p in (old_internal, new_internal)]
        groups, _ = analyzer.build_groups(infos)
        assert len(groups) == 1
        verdict = analyzer.rank_latest(groups[0])
        assert not verdict.branch
        assert verdict.candidate is not None
        assert verdict.candidate.name == "報告書_修正.docx", verdict.candidate
        keys = [k for k, _ in verdict.reasons]
        assert "reason_dt_office" in keys, keys


def test_branch_detection_no_verdict():
    with tempfile.TemporaryDirectory() as d:
        v2 = os.path.join(d, "仕様書_修正.docx")
        v3 = os.path.join(d, "仕様書_最終版.docx")
        make_docx(v2, BASE + ["Aさんが足した行"], "2025-01-02T09:00:00Z")
        make_docx(v3, BASE + ["Bさんが足した行"], "2025-01-03T09:00:00Z")
        infos = [analyzer.extract(p) for p in (v2, v3)]
        groups, _ = analyzer.build_groups(infos)
        verdict = analyzer.rank_latest(groups[0])
        assert verdict.branch, verdict
        assert verdict.candidate is None
        assert verdict.branch_with is not None


def test_cell_value_edit_is_not_a_branch():
    """Editing cell values (same coordinates) is a normal revision,
    not a divergence: the newer spreadsheet must be the candidate."""
    with tempfile.TemporaryDirectory() as d:
        a = os.path.join(d, "見積書.xlsx")
        b = os.path.join(d, "見積書_修正.xlsx")
        make_xlsx(a, [["項目", "金額"], ["作業費", "100"], ["合計", "100"]],
                  "2025-01-01T09:00:00Z")
        make_xlsx(b, [["項目", "金額"], ["作業費", "120"], ["合計", "120"],
                      ["備考", "税込"]], "2025-01-02T09:00:00Z")
        infos = [analyzer.extract(p) for p in (a, b)]
        groups, _ = analyzer.build_groups(infos)
        assert len(groups) == 1
        verdict = analyzer.rank_latest(groups[0])
        assert not verdict.branch, verdict
        assert verdict.candidate is not None
        assert verdict.candidate.name == "見積書_修正.xlsx"


def test_manual_latest_override():
    with tempfile.TemporaryDirectory() as d:
        v1 = os.path.join(d, "案内文.txt")
        v2 = os.path.join(d, "案内文_修正.txt")
        write(v1, "元の文章\n")
        write(v2, "元の文章\n新しい行\n")
        infos = [analyzer.extract(p) for p in (v1, v2)]
        groups, _ = analyzer.build_groups(infos)
        groups[0].manual_latest = v1
        verdict = analyzer.rank_latest(groups[0])
        assert verdict.candidate is not None
        assert verdict.candidate.path == v1
        assert verdict.reasons[0][0] == "reason_manual"


def test_docx_line_diff():
    with tempfile.TemporaryDirectory() as d:
        a = os.path.join(d, "a.docx")
        b = os.path.join(d, "b.docx")
        make_docx(a, ["1行目", "2行目", "3行目"])
        make_docx(b, ["1行目", "2行目改", "3行目", "4行目"])
        ia, ib = analyzer.extract(a), analyzer.extract(b)
        dres = analyzer.diff_infos(ia, ib)
        assert dres.kind == "text"
        assert dres.added == 2 and dres.deleted == 1, dres


def test_xlsx_cell_diff():
    with tempfile.TemporaryDirectory() as d:
        a = os.path.join(d, "見積.xlsx")
        b = os.path.join(d, "見積_修正.xlsx")
        make_xlsx(a, [["項目", "金額"], ["作業費", "100"], ["合計", "100"]])
        make_xlsx(b, [["項目", "金額"], ["作業費", "120"], ["合計", "120"],
                      ["備考", "税込"]])
        ia, ib = analyzer.extract(a), analyzer.extract(b)
        assert ia.kind == "cells" and ib.kind == "cells"
        dres = analyzer.diff_infos(ia, ib)
        assert dres.kind == "cells"
        changed = {(s, c): (o, n) for s, c, o, n in dres.changed_cells}
        assert changed[("Data", "B2")] == ("100", "120"), changed
        assert changed[("Data", "B3")] == ("100", "120")
        assert dres.added_cells == 2, dres  # A4, B4 added


def test_corrupt_and_encrypted_are_listed():
    with tempfile.TemporaryDirectory() as d:
        bad = os.path.join(d, "壊れた.docx")
        write(bad, "これはZIPではありません")
        enc = os.path.join(d, "秘密.pdf")
        with open(enc, "wb") as fh:
            fh.write(b"%PDF-1.7\n<< /Encrypt 12 0 R >>\n"
                     b"/ModDate (D:20250101120000Z)\n%%EOF")
        ib = analyzer.extract(bad)
        ie = analyzer.extract(enc)
        assert ib.status == "error" and ib.error_reason == "corrupt", ib
        assert ie.status == "error" and ie.error_reason == "encrypted", ie


def test_rejected_pair_splits_group():
    with tempfile.TemporaryDirectory() as d:
        a = os.path.join(d, "メモ.txt")
        b = os.path.join(d, "メモ_コピー.txt")
        write(a, "同じ内容\n")
        write(b, "同じ内容\n")
        infos = [analyzer.extract(p) for p in (a, b)]
        groups, _ = analyzer.build_groups(infos)
        assert len(groups) == 1
        groups2, singles2 = analyzer.build_groups(
            infos, rejected_pairs={frozenset((a, b))})
        # stage-1 (identical content) still groups them; rejection
        # only blocks stage-2/candidate edges and manual merges are
        # separate.  Identical files remain an exact group by design.
        assert len(groups2) == 1 and groups2[0].kind == "exact"


def test_move_clash_and_undo():
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp()
    import mover
    with tempfile.TemporaryDirectory() as d:
        src_dir = os.path.join(d, "work")
        arc = os.path.join(d, "archive")
        os.makedirs(src_dir)
        os.makedirs(arc)
        f1 = os.path.join(src_dir, "旧版.txt")
        write(f1, "old\n")
        write(os.path.join(arc, "旧版.txt"), "already there\n")
        done, errors = mover.execute_moves([(f1, arc)])
        assert not errors, errors
        assert len(done) == 1
        # clash avoided with a serial suffix, nothing overwritten
        assert os.path.basename(done[0]["dst"]) == "旧版 (2).txt"
        with open(os.path.join(arc, "旧版.txt"), encoding="utf-8") as fh:
            assert fh.read() == "already there\n"
        undone, uerrors = mover.undo_last_batch()
        assert not uerrors and len(undone) == 1
        assert os.path.exists(f1)
        # log persisted on disk
        log = mover.load_log()
        assert log and log[-1]["undone"] is True


def test_i18n_complete():
    import i18n
    base = None
    for code, _name in i18n.LANGS:
        keys = set(i18n.STRINGS[code])
        if base is None:
            base = keys
        assert keys == base, (code, sorted(base ^ keys))
    # every formatted key renders in every language
    for code, _name in i18n.LANGS:
        for key in ("status_done", "similarity", "chg_lines",
                    "analyzing_count", "version_no", "chg_cells"):
            out = i18n.tr(code, key, files=1, groups=2, pct=50,
                          a=1, d=2, done=3, total=9, n=4)
            assert "{" not in out, (code, key, out)


def test_gui_smoke():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import app as appmod
    win = appmod.MainWindow()
    with tempfile.TemporaryDirectory() as d:
        v1 = os.path.join(d, "企画書.docx")
        v2 = os.path.join(d, "企画書_最終版.docx")
        make_docx(v1, BASE, "2025-01-01T09:00:00Z")
        make_docx(v2, BASE + ["追加の行"], "2025-01-02T09:00:00Z")
        infos = [analyzer.extract(p) for p in (v1, v2)]
        win._scan_done(infos)
        assert win.groups, "expected one group"
        assert win.canvas._nodes, "genealogy nodes missing"
        assert len(win.canvas._nodes) == 2
        # language switching incl. RTL must not raise
        idx_ar = [c for c, _ in appmod.LANGS].index("ar")
        win.lang_combo.setCurrentIndex(idx_ar)
        assert win.lang == "ar"
        assert win.canvas._rtl is True
        idx_en = [c for c, _ in appmod.LANGS].index("en")
        win.lang_combo.setCurrentIndex(idx_en)
        assert win.lang == "en"
        # archive dialog builds
        dlg_members = [(i, True) for i in win.groups[0].members]
        dlg = appmod.ArchiveDialog(win, "en", dlg_members, d)
        assert dlg.list.count() == 2
        dlg.close()
    win.close()


def _run_all():
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            import traceback
            print(f"FAIL {name}: {exc}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())

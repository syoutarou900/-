# -*- coding: utf-8 -*-
"""DropLauncher core logic (no Qt imports) - all processing functions.
Generic Windows app: no hardcoded user names / machine names / absolute paths.
Known folders are resolved via environment / Path.home() only.
"""
import copy, csv, datetime, email, html, json, os, re, shutil, subprocess, sys, zipfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent

try:
    from i18n_data import t as _it, LANG_ORDER as _LANGS
except Exception:  # i18n_data ships with the app; fallback keeps core usable alone
    _LANGS = ["ja"]
    def _it(lang, key, **kw):
        return key

def _lang(settings):
    if isinstance(settings, dict):
        lang = settings.get("language") or "ja"
        return lang if lang in _LANGS else "ja"
    return "ja"

def _t(settings, key, **kw):
    return _it(_lang(settings), key, **kw)

def app_base_dir():
    """Writable base dir for settings/logs: beside the exe/app when writable (portable),
    else %LOCALAPPDATA%/DropLauncher, else ~/.DropLauncher. No admin rights needed.
    macOS (darwin) always uses the standard ~/Library/Application Support/DropLauncher,
    because a built .app bundle is not a writable location."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "DropLauncher"
        try:
            base.mkdir(parents=True, exist_ok=True)
            return base
        except Exception:
            return Path.home()
    try:
        test = APP_DIR / ".dl_write_test"
        test.write_text("x", encoding="utf-8"); test.unlink()
        return APP_DIR
    except Exception:
        pass
    local = os.environ.get("LOCALAPPDATA")
    base = (Path(local) / "DropLauncher") if local else (Path.home() / ".DropLauncher")
    try:
        base.mkdir(parents=True, exist_ok=True)
        return base
    except Exception:
        return Path.home()

BASE_DIR = app_base_dir()

def default_documents_dir():
    """Resolve Documents via env where possible (Windows Known Folder fallbacks), else ~/Documents."""
    # OneDrive / redirected folders may set USERPROFILE; Path.home() is locale-independent.
    docs = Path.home() / "Documents"
    return docs

def default_output_base():
    try:
        docs = default_documents_dir()
        docs.mkdir(parents=True, exist_ok=True)
        test = docs / ".dl_write_test"
        test.write_text("x", encoding="utf-8"); test.unlink()
        return str(docs / "DropLauncher-Out")
    except Exception:
        return str(BASE_DIR / "output")

DEFAULT_SETTINGS = {
    "output_base": "",
    "project": "作業",
    "sort_mode": "move",
    "sort_subfolder": "ext_date",
    "image_max_width": 1200,
    "image_target_kb": 500,
    "image_format": "JPG",
    "video_preset": "mp4",
    "soffice_path": "",
    "always_on_top": True,
    "language": "ja",
}

def settings_path():
    return BASE_DIR / "settings.json"

def load_settings(path=None):
    p = Path(path) if path else settings_path()
    s = dict(DEFAULT_SETTINGS)
    # also accept a settings.json beside the app for portable use
    alt = APP_DIR / "settings.json"
    src = p if p.exists() else (alt if alt.exists() else p)
    if src.exists():
        try:
            s.update(json.loads(src.read_text(encoding="utf-8")))
        except Exception:
            pass
    if not s.get("output_base"):
        s["output_base"] = default_output_base()
    return s

def save_settings(s, path=None):
    p = Path(path) if path else settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    return p

def out_dir(settings, sub):
    d = Path(settings["output_base"]) / sub
    d.mkdir(parents=True, exist_ok=True)
    return d

def today_str():
    return datetime.date.today().strftime("%Y%m%d")

def log_error(msg):
    try:
        with open(BASE_DIR / "DropLauncher-error.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {msg}\n")
    except Exception:
        pass

def unique_path(path):
    path = Path(path)
    if not path.exists():
        return path
    i = 2
    while True:
        cand = path.with_name(f"{path.stem}_{i}{path.suffix}")
        if not cand.exists():
            return cand
        i += 1

# ---------------- 1. Transcribe ----------------
def extract_text_from_file(path, lang="ja"):
    path = Path(path)
    ext = path.suffix.lower()
    text_parts, tables = [], []
    if ext == ".pdf":
        import fitz
        doc = fitz.open(path)
        for pi, page in enumerate(doc):
            t = page.get_text()
            text_parts.append(f"--- ページ {pi+1} ---\n{t}")
            try:
                for tab in page.find_tables().tables:
                    rows = tab.extract()
                    if rows:
                        tables.append([[("" if c is None else str(c)) for c in r] for r in rows])
            except Exception:
                pass
        doc.close()
    elif ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        for ws in wb.worksheets:
            rows = []
            for row in ws.iter_rows(values_only=True):
                r = [("" if c is None else str(c)) for c in row]
                if any(c.strip() for c in r):
                    rows.append(r)
            if rows:
                tables.append(rows)
                text_parts.append(f"--- シート {ws.title} ---\n" + "\n".join("\t".join(r) for r in rows))
        wb.close()
    elif ext == ".csv":
        rows = []
        for enc in ("utf-8-sig", "cp932", "utf-8"):
            try:
                with open(path, newline="", encoding=enc) as f:
                    rows = list(csv.reader(f))
                break
            except Exception:
                rows = []
        tables.append(rows)
        text_parts.append("\n".join(",".join(r) for r in rows))
    elif ext == ".eml":
        msg = email.message_from_binary_file(open(path, "rb"))
        text_parts.append(f"件名: {msg.get('Subject','')}\n差出人: {msg.get('From','')}\n宛先: {msg.get('To','')}\n")
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        body += part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="replace")
                    except Exception:
                        pass
        else:
            try:
                body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", errors="replace")
            except Exception:
                body = str(msg.get_payload())
        text_parts.append(body)
    elif ext in (".txt", ".md", ".log"):
        for enc in ("utf-8-sig", "cp932", "utf-8"):
            try:
                text_parts.append(path.read_text(encoding=enc)); break
            except Exception:
                continue
    else:
        raise ValueError(_it(lang, "err_transcribe_unsupported", ext=ext))
    return "\n".join(text_parts), tables

def styled_header_cell(cell):
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    cell.font = Font(bold=True, color="FFFFFF")
    cell.fill = PatternFill("solid", fgColor="4472C4")
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Side(style="thin", color="B0B0B0")
    cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)

def write_styled_xlsx(tables, text, dest):
    import openpyxl
    wb = openpyxl.Workbook()
    if tables:
        wb.remove(wb.active)
        for i, rows in enumerate(tables):
            ws = wb.create_sheet(title=f"表{i+1}"[:31])
            for r, row in enumerate(rows):
                for c, val in enumerate(row):
                    cell = ws.cell(row=r+1, column=c+1, value=val)
                    if r == 0:
                        styled_header_cell(cell)
            for c in range(len(rows[0]) if rows else 0):
                ws.column_dimensions[openpyxl.utils.get_column_letter(c+1)].width = 22
        ws = wb.create_sheet(title="全文テキスト")
        for i, line in enumerate(text.splitlines()):
            ws.cell(row=i+1, column=1, value=line)
        ws.column_dimensions["A"].width = 110
    else:
        ws = wb.active; ws.title = "全文テキスト"
        for i, line in enumerate(text.splitlines()):
            ws.cell(row=i+1, column=1, value=line)
        ws.column_dimensions["A"].width = 110
    wb.save(dest)

def copy_xlsx_styled(src, dest):
    """Excel->Excel styled copy preserving value/font/fill/border/alignment/number_format/widths/merges."""
    import openpyxl
    wb = openpyxl.load_workbook(src)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.has_style:
                    cell.font = copy.copy(cell.font)
                    cell.fill = copy.copy(cell.fill)
                    cell.border = copy.copy(cell.border)
                    cell.alignment = copy.copy(cell.alignment)
                    cell.protection = copy.copy(cell.protection)
    wb.save(dest)
    return dest

def transcribe_file(path, settings, log=lambda m: None):
    path = Path(path)
    out = out_dir(settings, "transcribe")
    stem = f"{today_str()}_{path.stem}"
    outputs = []
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        dest = unique_path(out / f"{stem}_書式コピー.xlsx")
        copy_xlsx_styled(path, dest); outputs.append(dest)
        log(_t(settings, "log_excel_copy", name=dest.name))
    text, tables = extract_text_from_file(path, lang=_lang(settings))
    xlsx = unique_path(out / f"{stem}.xlsx")
    write_styled_xlsx(tables, text, xlsx); outputs.append(xlsx)
    txt = unique_path(out / f"{stem}.txt")
    txt.write_text(text, encoding="utf-8"); outputs.append(txt)
    if tables:
        csvo = unique_path(out / f"{stem}.csv")
        with open(csvo, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            for rows in tables:
                w.writerows(rows); w.writerow([])
        outputs.append(csvo)
    log(_t(settings, "log_transcribe", name=path.name, chars=len(text), tables=len(tables)))
    return outputs

# ---------------- 2. Sort & rename ----------------
HISTORY_FILE = "history.json"

def _history_path(settings):
    return Path(settings["output_base"]) / HISTORY_FILE

def load_history(settings):
    p = _history_path(settings)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_history(settings, hist):
    Path(settings["output_base"]).mkdir(parents=True, exist_ok=True)
    _history_path(settings).write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")

def sort_rename_files(files, settings, log=lambda m: None):
    base = Path(settings["output_base"]) / "sorted"
    base.mkdir(parents=True, exist_ok=True)
    date = today_str(); project = settings.get("project") or "作業"
    mode = settings.get("sort_subfolder", "ext_date")
    ops = []
    seq = 1
    existing = []
    for root, _dirs, fnames in os.walk(base):
        existing.extend(fnames)
    pat = re.compile(rf"^{date}_{re.escape(project)}_(\d{{3}})")
    for name in existing:
        m = pat.match(name)
        if m:
            seq = max(seq, int(m.group(1)) + 1)
    for f in files:
        f = Path(f)
        if not f.exists():
            log(_t(settings, "log_not_found", path=f)); continue
        sub = base
        ext = f.suffix.lower().lstrip(".") or "noext"
        if mode in ("ext", "ext_date"):
            sub = sub / ext
        if mode in ("date", "ext_date"):
            sub = sub / date
        sub.mkdir(parents=True, exist_ok=True)
        while True:
            dest = sub / f"{date}_{project}_{seq:03d}{f.suffix.lower()}"
            seq += 1
            if not dest.exists():
                break
        if settings.get("sort_mode", "move") == "copy":
            shutil.copy2(f, dest); ops.append({"op": "copy", "src": str(f), "dst": str(dest)})
        else:
            shutil.move(str(f), str(dest)); ops.append({"op": "move", "src": str(f), "dst": str(dest)})
        log(_t(settings, "log_sort", name=f.name, dest=dest))
    if ops:
        hist = load_history(settings)
        hist.append({"time": datetime.datetime.now().isoformat(timespec="seconds"), "ops": ops})
        save_history(settings, hist)
    return ops

def undo_last(settings, log=lambda m: None):
    hist = load_history(settings)
    if not hist:
        log(_t(settings, "log_undo_none")); return 0
    batch = hist.pop()
    n = 0
    for op in reversed(batch["ops"]):
        dst, src = Path(op["dst"]), Path(op["src"])
        try:
            if op["op"] == "move" and dst.exists():
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(unique_path(src) if src.exists() else src)); n += 1
            elif op["op"] == "copy" and dst.exists():
                dst.unlink(); n += 1
        except Exception as e:
            log(_t(settings, "log_undo_failed", path=dst, error=e))
    save_history(settings, hist)
    log(_t(settings, "log_undo_done", count=n))
    return n

# ---------------- 3. Report aggregation ----------------
def aggregate_report(path, settings, log=lambda m: None):
    path = Path(path)
    rows = []
    if path.suffix.lower() == ".csv":
        for enc in ("utf-8-sig", "cp932", "utf-8"):
            try:
                with open(path, newline="", encoding=enc) as f:
                    rows = list(csv.reader(f)); break
            except Exception:
                rows = []
    else:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active
        for row in ws.iter_rows(values_only=True):
            rows.append([("" if c is None else c) for c in row])
        wb.close()
    if not rows:
        raise ValueError(_t(settings, "err_empty_data"))
    header = [str(h) for h in rows[0]]
    data = rows[1:]
    sums = {}
    for ci, h in enumerate(header):
        total, cnt = 0.0, 0
        for r in data:
            if ci < len(r):
                try:
                    v = float(str(r[ci]).replace(",", ""))
                    total += v; cnt += 1
                except Exception:
                    pass
        if cnt:
            sums[h or _t(settings, "col_fallback", n=ci+1)] = total
    status_idx = [i for i, h in enumerate(header) if any(k in h.lower() for k in ("status", "状態", "進捗", "ステータス"))]
    done = 0
    for r in data:
        cells = [str(r[i]) for i in status_idx if i < len(r)] if status_idx else [str(c) for c in r]
        if any("完了" in c for c in cells):
            done += 1
    out = out_dir(settings, "report")
    date_disp = datetime.date.today().strftime("%Y-%m-%d")
    lines = [_t(settings, "report_title", date=date_disp), _t(settings, "report_file", name=path.name),
             _t(settings, "report_rows", count=len(data)), _t(settings, "report_done", count=done)]
    for k, v in sums.items():
        lines.append(_t(settings, "report_sum", name=k, value=(f"{v:,.2f}" if v != int(v) else f"{int(v):,}")))
    report_text = "\n".join(lines) + "\n"
    txt = unique_path(out / f"{today_str()}_日報集計.txt")
    txt.write_text(report_text, encoding="utf-8")
    import openpyxl
    summ = out / "集計サマリー.xlsx"
    if summ.exists():
        wb = openpyxl.load_workbook(summ); ws = wb.active
        hdr_len = ws.max_column
        existing_hdr = [str(ws.cell(row=1, column=c+1).value or "") for c in range(hdr_len)]
        keys = [h[:-2] if h.endswith("合計") else h for h in existing_hdr[4:]]
        for k in sums:
            if k not in keys:
                keys.append(k)
        new_hdr = ["日時", "ファイル", "件数", "完了件数"] + [f"{k}合計" for k in keys]
        if existing_hdr != new_hdr:
            for c, val in enumerate(new_hdr):
                cell = ws.cell(row=1, column=c+1, value=val)
        rowvals = [datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), path.name, len(data), done] + [sums.get(k, "") for k in keys]
        ws.append(rowvals)
    else:
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = "集計"
        hdr = ["日時", "ファイル", "件数", "完了件数"] + [f"{k}合計" for k in sums]
        for c, val in enumerate(hdr):
            cell = ws.cell(row=1, column=c+1, value=val); styled_header_cell(cell)
        ws.append([datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), path.name, len(data), done] + [sums[k] for k in sums])
    wb.save(summ)
    log(_t(settings, "log_report", name=path.name, rows=len(data), done=done))
    return {"rows": len(data), "done": done, "sums": sums, "report_text": report_text, "txt": txt, "summary": summ}

# ---------------- 4. Image conversion ----------------
def convert_image(path, settings, log=lambda m: None):
    from PIL import Image, ImageOps
    path = Path(path)
    out = out_dir(settings, "images")
    fmt = (settings.get("image_format") or "JPG").upper()
    ext_map = {"JPG": ".jpg", "JPEG": ".jpg", "WEBP": ".webp", "PNG": ".png"}
    ext = ext_map.get(fmt, ".jpg")
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    maxw = int(settings.get("image_max_width") or 1200)
    if im.width > maxw:
        h = round(im.height * maxw / im.width)
        im = im.resize((maxw, h), Image.LANCZOS)
    dest = unique_path(out / f"{path.stem}{ext}")
    target = int(settings.get("image_target_kb") or 500) * 1024
    if fmt in ("JPG", "JPEG"):
        rgb = im.convert("RGB") if im.mode != "RGB" else im
        q = 90
        while True:
            rgb.save(dest, "JPEG", quality=q)
            if dest.stat().st_size <= target or q <= 20:
                break
            q -= 10
    elif fmt == "WEBP":
        q = 90
        while True:
            im.save(dest, "WEBP", quality=q)
            if dest.stat().st_size <= target or q <= 20:
                break
            q -= 10
    else:
        im.save(dest, "PNG")
    log(_t(settings, "log_image", name=path.name, dest=dest.name, kb=dest.stat().st_size//1024))
    return dest

# ---------------- 5. PDF tools ----------------
def pdf_merge(files, settings, log=lambda m: None):
    import fitz
    out = out_dir(settings, "pdf")
    dest = unique_path(out / f"{today_str()}_{settings.get('project') or '作業'}_結合.pdf")
    doc = fitz.open()
    for f in files:
        src = fitz.open(f)
        doc.insert_pdf(src); src.close()
    doc.save(dest); doc.close()
    log(_t(settings, "log_pdf_merge", count=len(files), name=dest.name))
    return dest

def pdf_split(path, settings, log=lambda m: None):
    import fitz
    path = Path(path)
    out = out_dir(settings, "pdf") / f"{path.stem}_分割"
    out.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(path)
    outs = []
    for i in range(doc.page_count):
        d = fitz.open(); d.insert_pdf(doc, from_page=i, to_page=i)
        p = out / f"{path.stem}_{i+1:03d}.pdf"
        d.save(p); d.close(); outs.append(p)
    doc.close()
    log(_t(settings, "log_pdf_split", name=path.name, count=len(outs)))
    return outs

def pdf_extract_text(path, settings, log=lambda m: None):
    import fitz
    path = Path(path)
    out = out_dir(settings, "pdf")
    doc = fitz.open(path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    dest = unique_path(out / f"{path.stem}.txt")
    dest.write_text(text, encoding="utf-8")
    log(_t(settings, "log_pdf_text", name=path.name, dest=dest.name))
    return dest

# ---------------- 6. Video conversion (ffmpeg) ----------------
def find_ffmpeg(settings=None):
    if sys.platform == "darwin":
        # macOS: no .exe candidates. Bundled tools first, then Homebrew
        # (Finder-launched apps have a minimal PATH, so check the well-known
        # Homebrew locations explicitly), then PATH, then imageio-ffmpeg.
        for cand in (APP_DIR / "tools" / "ffmpeg", BASE_DIR / "tools" / "ffmpeg",
                     Path("/opt/homebrew/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg")):
            if cand.exists():
                return str(cand)
        w = shutil.which("ffmpeg")
        if w:
            return w
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None
    for cand in (APP_DIR / "tools" / "ffmpeg.exe", APP_DIR / "tools" / "ffmpeg",
                 BASE_DIR / "tools" / "ffmpeg.exe", BASE_DIR / "tools" / "ffmpeg"):
        if cand.exists():
            return str(cand)
    w = shutil.which("ffmpeg")
    if w:
        return w
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

def convert_video(path, settings, log=lambda m: None, preset=None):
    path = Path(path)
    ffmpeg = find_ffmpeg(settings)
    if not ffmpeg:
        raise RuntimeError(_t(settings, "err_ffmpeg_missing"))
    preset = preset or settings.get("video_preset", "mp4")
    out = out_dir(settings, "video")
    if preset == "mp3":
        dest = unique_path(out / f"{path.stem}.mp3")
        cmd = [ffmpeg, "-y", "-i", str(path), "-vn", "-codec:a", "libmp3lame", "-q:a", "2", str(dest)]
    elif preset == "gif":
        dest = unique_path(out / f"{path.stem}.gif")
        cmd = [ffmpeg, "-y", "-i", str(path), "-vf", "fps=10,scale=480:-1:flags=lanczos", "-t", "10", str(dest)]
    elif preset == "compress":
        dest = unique_path(out / f"{path.stem}_720p.mp4")
        cmd = [ffmpeg, "-y", "-i", str(path), "-vf", "scale=-2:min(720\\,ih)", "-c:v", "libx264", "-crf", "28", "-preset", "medium", "-c:a", "aac", "-b:a", "128k", str(dest)]
    else:
        dest = unique_path(out / f"{path.stem}.mp4")
        cmd = [ffmpeg, "-y", "-i", str(path), "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-c:a", "aac", "-b:a", "160k", str(dest)]
    log(_t(settings, "log_video_start", preset=preset, name=path.name))
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          encoding="utf-8", errors="replace",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if proc.returncode != 0 or not dest.exists():
        log_error(proc.stdout[-3000:] if proc.stdout else "ffmpeg failed")
        raise RuntimeError(_t(settings, "err_ffmpeg_failed"))
    log(_t(settings, "log_video_done", name=dest.name, kb=dest.stat().st_size//1024))
    return dest

# ---------------- 7. Excel format-preserving conversion ----------------
def _program_files_dirs():
    dirs = []
    for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        v = os.environ.get(var)
        if v:
            dirs.append(Path(v))
    return dirs

def find_soffice(settings=None):
    if sys.platform == "darwin":
        # macOS: LibreOffice lives in /Applications or via Homebrew;
        # there are no Program Files folders or .exe binaries.
        cands = []
        if settings and settings.get("soffice_path"):
            cands.append(settings["soffice_path"])
        w = shutil.which("soffice")
        if w:
            cands.append(w)
        cands.append("/Applications/LibreOffice.app/Contents/MacOS/soffice")
        cands.append("/opt/homebrew/bin/soffice")
        cands.append("/usr/local/bin/soffice")
        cands.append(str(APP_DIR / "tools" / "soffice"))
        cands.append(str(BASE_DIR / "tools" / "soffice"))
        for c in cands:
            if c and Path(c).exists():
                return c
        return None
    cands = []
    if settings and settings.get("soffice_path"):
        cands.append(settings["soffice_path"])
    w = shutil.which("soffice") or shutil.which("soffice.exe")
    if w:
        cands.append(w)
    for base in _program_files_dirs():
        cands.append(str(base / "LibreOffice" / "program" / "soffice.exe"))
        cands.append(str(base / "LibreOffice" / "program" / "soffice"))
    cands.append(str(APP_DIR / "tools" / "soffice.exe"))
    cands.append(str(BASE_DIR / "tools" / "soffice.exe"))
    for c in cands:
        if c and Path(c).exists():
            return c
    return None

def xlsx_to_csv(path, settings, log=lambda m: None):
    import openpyxl
    path = Path(path)
    out = out_dir(settings, "excel")
    wb = openpyxl.load_workbook(path, data_only=True)
    outs = []
    for ws in wb.worksheets:
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", ws.title)
        dest = unique_path(out / f"{path.stem}_{safe_title}.csv")
        with open(dest, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            for row in ws.iter_rows(values_only=True):
                w.writerow([("" if c is None else c) for c in row])
        outs.append(dest)
    wb.close()
    log(_t(settings, "log_excel_csv", name=path.name, count=len(outs)))
    return outs

def _css_color(argb):
    if not argb or not isinstance(argb, str) or len(argb) < 8:
        return None
    rgb = argb[2:]
    return "#" + rgb if re.fullmatch(r"[0-9A-Fa-f]{6}", rgb) else None

def xlsx_to_html(path, settings, log=lambda m: None):
    import openpyxl
    path = Path(path)
    out = out_dir(settings, "excel")
    wb = openpyxl.load_workbook(path, data_only=True)
    parts = ["<!DOCTYPE html><html><head><meta charset='utf-8'>",
             f"<title>{html.escape(path.stem)}</title>",
             "<style>table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:4px 8px}</style></head><body>"]
    for ws in wb.worksheets:
        parts.append(f"<h2>{html.escape(ws.title)}</h2><table>")
        merged = {}
        try:
            for rng in ws.merged_cells.ranges:
                merged[(rng.min_row, rng.min_col)] = (rng.max_row - rng.min_row + 1, rng.max_col - rng.min_col + 1)
        except Exception:
            pass
        skip = set()
        for rng_cells in []:
            pass
        for row in ws.iter_rows():
            parts.append("<tr>")
            for cell in row:
                key = (cell.row, cell.column)
                if key in skip:
                    continue
                val = cell.value
                disp = ""
                if val is not None:
                    if isinstance(val, (datetime.datetime, datetime.date)):
                        disp = val.strftime("%Y-%m-%d")
                    elif isinstance(val, float) and cell.number_format and "%" in cell.number_format:
                        disp = f"{val*100:.1f}%"
                    elif isinstance(val, float) and cell.number_format and ("," in cell.number_format or "#" in cell.number_format):
                        disp = f"{val:,.2f}".rstrip("0").rstrip(".")
                    else:
                        disp = str(val)
                styles = []
                try:
                    if cell.font and cell.font.bold:
                        styles.append("font-weight:bold")
                    if cell.font and cell.font.size:
                        styles.append(f"font-size:{cell.font.size}pt")
                    if cell.font and cell.font.color:
                        col = _css_color(getattr(cell.font.color, "rgb", None))
                        if col: styles.append(f"color:{col}")
                    if cell.fill and cell.fill.fgColor:
                        col = _css_color(getattr(cell.fill.fgColor, "rgb", None))
                        if col and col != "#000000": styles.append(f"background-color:{col}")
                    if cell.alignment and cell.alignment.horizontal:
                        styles.append(f"text-align:{cell.alignment.horizontal}")
                except Exception:
                    pass
                span = ""
                if key in merged:
                    rs, cs = merged[key]
                    if rs > 1: span += f" rowspan='{rs}'"
                    if cs > 1: span += f" colspan='{cs}'"
                    for rr in range(cell.row, cell.row + rs):
                        for cc in range(cell.column, cell.column + cs):
                            if (rr, cc) != key:
                                skip.add((rr, cc))
                style = f" style='{';'.join(styles)}'" if styles else ""
                parts.append(f"<td{span}{style}>{html.escape(disp)}</td>")
            parts.append("</tr>")
        parts.append("</table>")
    parts.append("</body></html>")
    wb.close()
    dest = unique_path(out / f"{path.stem}.html")
    dest.write_text("\n".join(parts), encoding="utf-8")
    log(_t(settings, "log_excel_html", name=dest.name))
    return dest

def convert_to_pdf(path, settings, log=lambda m: None):
    """Return (output_path, engine_name). Fallback = styled HTML (NOT pdf)."""
    path = Path(path)
    out = out_dir(settings, "excel")
    soffice = find_soffice(settings)
    if soffice:
        proc = subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out), str(path)],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              encoding="utf-8", errors="replace", timeout=300,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        pdf = out / f"{path.stem}.pdf"
        if proc.returncode == 0 and pdf.exists():
            log(_t(settings, "log_pdf_engine_libre", path=soffice))
            return pdf, "LibreOffice"
        log(_t(settings, "log_libre_failed", detail=(proc.stdout[-500:] if proc.stdout else "")))
    if sys.platform.startswith("win"):
        try:
            import win32com.client
            app = None; book = None
            ext = path.suffix.lower()
            if ext in (".xlsx", ".xlsm", ".xls"):
                app = win32com.client.Dispatch("Excel.Application"); app.Visible = False
                book = app.Workbooks.Open(str(path))
                pdf = unique_path(out / f"{path.stem}.pdf")
                book.ExportAsFixedFormat(0, str(pdf)); book.Close(False)
                log(_t(settings, "log_pdf_engine_excel"))
                return pdf, "Microsoft Excel COM"
            elif ext in (".docx", ".doc"):
                app = win32com.client.Dispatch("Word.Application"); app.Visible = False
                doc = app.Documents.Open(str(path))
                pdf = unique_path(out / f"{path.stem}.pdf")
                doc.ExportAsFixedFormat(str(pdf), 17); doc.Close(False)
                log(_t(settings, "log_pdf_engine_word"))
                return pdf, "Microsoft Word COM"
            elif ext in (".pptx", ".ppt"):
                app = win32com.client.Dispatch("PowerPoint.Application")
                pres = app.Presentations.Open(str(path), WithWindow=False)
                pdf = unique_path(out / f"{path.stem}.pdf")
                pres.ExportAsFixedFormat(str(pdf), 2); pres.Close()
                log(_t(settings, "log_pdf_engine_ppt"))
                return pdf, "Microsoft PowerPoint COM"
        except Exception as e:
            log(_t(settings, "log_com_failed", error=e))
        finally:
            try:
                if app is not None:
                    app.Quit()
            except Exception:
                pass
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        dest = xlsx_to_html(path, settings, log)
        log(_t(settings, "log_pdf_fallback"))
        return dest, "HTML fallback (not PDF)"
    raise RuntimeError("PDFに変換できるエンジン（LibreOffice / Microsoft Office）が見つかりませんでした")

def excel_convert(path, settings, log=lambda m: None):
    path = Path(path)
    outs = []
    if path.suffix.lower() in (".xlsx", ".xlsm", ".xls", ".docx", ".pptx", ".doc", ".ppt"):
        pdf_or_html, engine = convert_to_pdf(path, settings, log)
        outs.append(pdf_or_html)
        if path.suffix.lower() in (".xlsx", ".xlsm"):
            outs.extend(xlsx_to_csv(path, settings, log))
            if engine != "HTML fallback (not PDF)":
                outs.append(xlsx_to_html(path, settings, log))
    else:
        raise ValueError(_t(settings, "err_excel_unsupported", ext=path.suffix))
    return outs

# ---------------- 8. Archive ----------------
def archive_zip(files, settings, log=lambda m: None):
    out = out_dir(settings, "archive")
    dest = unique_path(out / f"{today_str()}_{settings.get('project') or '作業'}.zip")
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            f = Path(f)
            if f.is_dir():
                for root, _d, names in os.walk(f):
                    for n in names:
                        p = Path(root) / n
                        z.write(p, p.relative_to(f.parent))
            else:
                z.write(f, f.name)
    log(_t(settings, "log_zip_create", name=dest.name, kb=dest.stat().st_size//1024))
    return dest

def archive_extract(path, settings, log=lambda m: None):
    path = Path(path)
    base = out_dir(settings, "archive") / f"{path.stem}_展開"
    dest = unique_path(base) if (base.exists() and any(base.iterdir())) else base
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            try:
                decoded = name.encode("cp437").decode("cp932")
            except Exception:
                decoded = name
            target = (dest / decoded).resolve()
            if not str(target).startswith(str(dest.resolve())):
                log(_t(settings, "log_zip_skip", name=name)); continue
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True); continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(name) as srcf, open(target, "wb") as dstf:
                shutil.copyfileobj(srcf, dstf)
    log(_t(settings, "log_zip_extract", name=path.name, dest=dest))
    return dest

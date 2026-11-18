# -*- coding: utf-8 -*-
"""TranscribeGuard core: extraction, normalization, comparison, totals.

Pure Python (no Qt). Items are dicts: {"group": str, "field": str, "value": str}
Inputs are a parallel list of strings (what the person typed).
"""
import csv
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal, InvalidOperation

# ---------------------------------------------------------------- normalize

_FW_TABLE = {}
for i in range(0xFF01, 0xFF5F):
    _FW_TABLE[i] = i - 0xFEE0
_FW_TABLE[0x3000] = 0x20  # ideographic space -> space


def normalize(text):
    """Trim, full-width space/alphanumerics -> half-width, collapse spaces,
    lower-case latin. Used only for comparison, never shown to the user."""
    if text is None:
        return ""
    s = str(text).translate(_FW_TABLE)
    s = s.replace("　", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s.lower()


_NUMBER_STRIP = ["¥", "$", "€", "£", "￥", "円", " "]


def parse_number(text):
    """Return Decimal if the (normalized) text is a number, else None.
    Thousands separators ( , ) and a trailing 円 / currency symbol are ignored."""
    s = normalize(text)
    if not s:
        return None
    s = s.replace(",", "").replace("，", "")
    for ch in _NUMBER_STRIP:
        s = s.replace(ch, "")
    if s.endswith("円"):
        s = s[:-1]
    if not s:
        return None
    if not re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)", s):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def digit_count(text):
    """Number of digits in the numeric text (sign/point/separators ignored)."""
    n = parse_number(text)
    if n is None:
        return None
    s = normalize(text).replace(",", "").replace(" ", "")
    return len(re.sub(r"[^0-9]", "", s))


def is_numeric(text):
    return parse_number(text) is not None


# ---------------------------------------------------------------- compare

def compare(source, typed):
    """Return dict(status, reason, src_digits, in_digits, src_len, in_len, diff_pos).
    status: 'match' | 'mismatch' | 'empty'"""
    out = {"status": "empty", "reason": "", "src_digits": None, "in_digits": None,
           "src_len": 0, "in_len": 0, "diff_pos": None}
    ns, nt = normalize(source), normalize(typed)
    if nt == "":
        return out
    out["src_len"], out["in_len"] = len(ns), len(nt)
    sn, tn = parse_number(source), parse_number(typed)
    if sn is not None and tn is not None:
        if sn == tn:
            out["status"] = "match"
            return out
        out["status"] = "mismatch"
        out["src_digits"] = digit_count(source)
        out["in_digits"] = digit_count(typed)
        out["reason"] = "digits" if out["src_digits"] != out["in_digits"] else "number"
        return out
    if ns == nt:
        out["status"] = "match"
        return out
    out["status"] = "mismatch"
    out["reason"] = "text"
    for i, (a, b) in enumerate(zip(ns, nt)):
        if a != b:
            out["diff_pos"] = i + 1
            break
    if out["diff_pos"] is None:
        out["diff_pos"] = min(len(ns), len(nt)) + 1
    return out


def compute_stats(items, inputs):
    """total / done(match) / remaining(empty) / mismatch counts."""
    total = len(items)
    done = mismatch = remaining = 0
    for it, typed in zip(items, inputs):
        st = compare(it["value"], typed)["status"]
        if st == "match":
            done += 1
        elif st == "mismatch":
            mismatch += 1
        else:
            remaining += 1
    # items beyond inputs list count as remaining
    remaining += max(0, total - len(inputs))
    return {"total": total, "done": done, "remaining": remaining, "mismatch": mismatch}


def field_totals(items, inputs):
    """Per field-label totals for numeric source values.
    Returns list of {field, source_sum, typed_sum, match} (Decimal sums)."""
    order, agg = [], {}
    for idx, it in enumerate(items):
        sn = parse_number(it["value"])
        if sn is None:
            continue
        f = it["field"]
        if f not in agg:
            agg[f] = {"field": f, "source_sum": Decimal(0), "typed_sum": Decimal(0)}
            order.append(f)
        agg[f]["source_sum"] += sn
        typed = inputs[idx] if idx < len(inputs) else ""
        tn = parse_number(typed)
        if tn is not None:
            agg[f]["typed_sum"] += tn
    out = []
    for f in order:
        a = agg[f]
        a["match"] = a["source_sum"] == a["typed_sum"]
        out.append(a)
    return out


def fmt_num(d):
    """Decimal -> plain string without trailing zeros."""
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), "f")


def build_tsv(items, inputs):
    lines = ["group\tfield\tvalue"]
    for idx, it in enumerate(items):
        typed = inputs[idx] if idx < len(inputs) else ""
        lines.append("\t".join([it["group"], it["field"], typed]))
    return "\r\n".join(lines) + "\r\n"


# ---------------------------------------------------------------- extract

def _looks_numeric(s):
    return parse_number(s) is not None


def table_to_items(rows):
    """rows: list of list[str]. First row = header when it has a non-numeric
    cell. First column also becomes an item (nothing is dropped); the row's
    group label is its first cell."""
    rows = [[("" if c is None else str(c)).strip() for c in r] for r in rows]
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        return []
    items = []
    first = rows[0]
    has_header = any(c and not _looks_numeric(c) for c in first) and len(rows) > 1
    if has_header:
        header, data = first, rows[1:]
    else:
        header = [f"列{i+1}" for i in range(len(first))]
        data = rows
    width = max(len(header), max((len(r) for r in data), default=0))
    header += [f"列{i+1}" for i in range(len(header), width)]
    for r in data:
        r = r + [""] * (width - len(r))
        group = r[0]
        for col in range(width):
            if r[col] == "":
                continue
            items.append({"group": group, "field": header[col], "value": r[col]})
    return items


_KV_RE = re.compile(r"^(.{1,40}?)\s*[:：]\s*(.+)$")


def lines_to_items(lines):
    items, table_rows = [], []

    def flush_table():
        nonlocal table_rows
        if table_rows:
            items.extend(table_to_items(table_rows))
            table_rows = []

    for n, raw in enumerate(lines, 1):
        line = (raw or "").strip()
        if not line:
            continue
        cells = None
        if "\t" in line:
            cells = line.split("\t")
        elif "," in line:
            cells = next(csv.reader([line]))
        elif re.search(r"\S\s{2,}\S", line):
            cells = re.split(r"\s{2,}", line)
        if cells and len([c for c in cells if c.strip()]) >= 2:
            table_rows.append([c.strip() for c in cells])
            continue
        flush_table()
        m = _KV_RE.match(line)
        if m:
            items.append({"group": "", "field": m.group(1).strip(), "value": m.group(2).strip()})
        else:
            items.append({"group": "", "field": f"行{n}", "value": line})
    flush_table()
    return items


def _decode(data):
    for enc in ("utf-8-sig", "cp932", "utf-8"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _sniff_delimiter(text):
    first = text.splitlines()[0] if text.splitlines() else ""
    best, bestn = ",", 0
    for d in (",", "\t", ";"):
        n = first.count(d)
        if n > bestn:
            best, bestn = d, n
    return best


def extract_text(text):
    """TXT / pasted text / OCR text."""
    if not text or not text.strip():
        return []
    lines = text.splitlines()
    # If most non-empty lines contain a delimiter, treat as a table.
    nonempty = [ln for ln in lines if ln.strip()]
    delim_lines = sum(1 for ln in nonempty if ("\t" in ln or "," in ln or ";" in ln))
    if nonempty and delim_lines >= max(1, len(nonempty) // 2) and delim_lines >= 2:
        delim = _sniff_delimiter(text)
        rows = list(csv.reader(io.StringIO(text), delimiter=delim))
        items = table_to_items(rows)
        if items:
            return items
    return lines_to_items(lines)


def extract_csv(data_bytes):
    return extract_text(_decode(data_bytes))


def extract_xlsx(path):
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(values_only=True):
        rows.append([("" if c is None else _fmt_cell(c)) for c in row])
    wb.close()
    return table_to_items(rows)


def _fmt_cell(c):
    if isinstance(c, float) and c == int(c):
        return str(int(c))
    return str(c)


def extract_pdf(path):
    import fitz  # PyMuPDF
    doc = fitz.open(path)
    lines = []
    for page in doc:
        lines.extend(page.get_text().splitlines())
    doc.close()
    return lines_to_items(lines)


# ---------------------------------------------------------------- OCR
# Tesseract resolution order:
#   1. environment override TRANSCRIBEGUARD_TESSERACT_CMD (or ..._TESSERACT)
#   2. bundled copy below <base>/tesseract, where <base> is the
#      executable's folder when frozen, else this file's folder.  Windows
#      uses tesseract.exe; macOS deliberately ignores that Windows binary
#      and only accepts an extensionless Unix executable.
#   3. on macOS, the standard Homebrew locations.  These absolute paths
#      matter because Finder-launched apps do not inherit a login shell PATH.
#   4. system PATH ("tesseract")
# Tessdata mirrors it: TRANSCRIBEGUARD_TESSDATA_DIR override, then
# <base>/tesseract/tessdata, then <base>/tessdata, else tesseract's default.

_TESS_ENV_VARS = ("TRANSCRIBEGUARD_TESSERACT_CMD", "TRANSCRIBEGUARD_TESSERACT")
_MAC_TESSERACT_PATHS = (
    "/opt/homebrew/bin/tesseract",  # Homebrew on Apple Silicon
    "/usr/local/bin/tesseract",     # Homebrew on Intel Macs
)

UI_TO_TESS = {
    "ja": "jpn", "en": "eng", "es": "spa", "zh_CN": "chi_sim", "fr": "fra",
    "de": "deu", "pt": "por", "ru": "rus", "it": "ita", "tr": "tur",
    "ar": "ara", "id": "ind", "ko": "kor",
}


def _is_frozen(frozen):
    if frozen is not None:
        return frozen
    return bool(getattr(sys, "frozen", False))


def _base_dirs(frozen=None, exe_dir=None, app_dir=None):
    dirs = []
    if _is_frozen(frozen):
        dirs.append(exe_dir or os.path.dirname(os.path.abspath(sys.executable)))
    dirs.append(app_dir or os.path.dirname(os.path.abspath(__file__)))
    out = []
    for d in dirs:
        if d and d not in out:
            out.append(d)
    return out


def _platform_name(platform):
    return sys.platform if platform is None else platform


def tesseract_candidates(env=None, frozen=None, exe_dir=None, app_dir=None,
                         platform=None):
    env = os.environ if env is None else env
    platform = _platform_name(platform)
    cands = []
    for var in _TESS_ENV_VARS:
        if env.get(var):
            cands.append(env[var])
            break
    for base in _base_dirs(frozen, exe_dir, app_dir):
        # A bundled Windows tesseract.exe cannot run on macOS, so do not
        # offer it as a candidate there.  Windows keeps its original order.
        if platform != "darwin":
            cands.append(os.path.join(base, "tesseract", "tesseract.exe"))
        cands.append(os.path.join(base, "tesseract", "tesseract"))
    if platform == "darwin":
        cands.extend(_MAC_TESSERACT_PATHS)
    return cands


def find_tesseract(env=None, frozen=None, exe_dir=None, app_dir=None,
                   which=None, platform=None):
    """Path of the tesseract executable to use, or None if not found."""
    which = shutil.which if which is None else which
    for cand in tesseract_candidates(env, frozen, exe_dir, app_dir,
                                     platform=platform):
        if cand and os.path.isfile(cand):
            return cand
    return which("tesseract") or which("tesseract.exe")


def tessdata_candidates(env=None, frozen=None, exe_dir=None, app_dir=None):
    env = os.environ if env is None else env
    cands = []
    if env.get("TRANSCRIBEGUARD_TESSDATA_DIR"):
        cands.append(env["TRANSCRIBEGUARD_TESSDATA_DIR"])
    for base in _base_dirs(frozen, exe_dir, app_dir):
        cands.append(os.path.join(base, "tesseract", "tessdata"))
        cands.append(os.path.join(base, "tessdata"))
    return cands


def find_tessdata_dir(env=None, frozen=None, exe_dir=None, app_dir=None):
    """Folder holding .traineddata files for the bundled copy, or None."""
    for cand in tessdata_candidates(env, frozen, exe_dir, app_dir):
        try:
            if os.path.isdir(cand) and any(
                    f.endswith(".traineddata") for f in os.listdir(cand)):
                return cand
        except OSError:
            continue
    return None


def available_tess_langs(tessdata_dir):
    """Set of language codes with data in tessdata_dir, or None if unknown."""
    if not tessdata_dir:
        return None
    try:
        return {f[: -len(".traineddata")] for f in os.listdir(tessdata_dir)
                if f.endswith(".traineddata")}
    except OSError:
        return None


def ocr_lang_string(ui_lang="ja", tessdata_dir=None):
    """'jpn+eng' plus the tesseract code for the UI language when different.
    Codes without data in a known tessdata folder are dropped."""
    codes = ["jpn", "eng"]
    extra = UI_TO_TESS.get(ui_lang or "ja")
    if extra and extra not in codes:
        codes.append(extra)
    avail = available_tess_langs(tessdata_dir)
    if avail is not None:
        codes = [c for c in codes if c in avail]
    return "+".join(codes) if codes else "eng"


def ocr_available():
    return find_tesseract() is not None


def _run_tesseract(exe, image_path, langs, tessdata_dir):
    cmd = [exe, image_path, "stdout", "-l", langs, "--psm", "6"]
    if tessdata_dir:
        cmd += ["--tessdata-dir", tessdata_dir]
    kwargs = {"capture_output": True, "timeout": 180}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(cmd, **kwargs)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[:300])
    return proc.stdout.decode("utf-8", "replace")


def extract_image(path, ui_lang="ja"):
    """Returns (items, notice) where notice is 'ocr_unavailable' or ''."""
    exe = find_tesseract()
    if exe is None:
        return [], "ocr_unavailable"
    from PIL import Image
    tessdata_dir = find_tessdata_dir()
    try:
        img = Image.open(path)
        img_format = (img.format or "").upper()
        img.load()
    except Exception:
        return [], ""
    tmp = None
    try:
        if img_format not in ("PNG", "JPEG", "TIFF", "BMP"):
            fd, tmp = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            img.convert("RGB").save(tmp)
            image_path = tmp
        else:
            image_path = path
        lang_options = []
        for langs in (ocr_lang_string(ui_lang, tessdata_dir), "jpn+eng", "eng"):
            if langs and langs not in lang_options:
                lang_options.append(langs)
        for langs in lang_options:
            try:
                text = _run_tesseract(exe, image_path, langs, tessdata_dir)
            except Exception:
                text = ""
            if text.strip():
                return extract_text(text), ""
        return [], ""
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass


def extract_file(path, ui_lang="ja"):
    """Dispatch by extension. Returns (items, notice).
    ui_lang selects the OCR language for images (see UI_TO_TESS)."""
    ext = path.lower().rsplit(".", 1)[-1] if "." in path else ""
    if ext == "pdf":
        return extract_pdf(path), ""
    if ext == "xlsx":
        return extract_xlsx(path), ""
    if ext == "csv":
        with open(path, "rb") as fh:
            return extract_csv(fh.read()), ""
    if ext == "txt":
        with open(path, "rb") as fh:
            return extract_text(_decode(fh.read())), ""
    if ext in ("png", "jpg", "jpeg", "bmp", "gif", "webp"):
        return extract_image(path, ui_lang)
    raise ValueError(f"unsupported extension: {ext}")


# ---------------------------------------------------------------- sample

def sample_items():
    rows = [
        ("ノート A5", "10", "150"),
        ("ボールペン", "20", "120"),
        ("コピー用紙 A4", "5", "480"),
        ("クリアファイル", "12", "80"),
    ]
    items = [
        {"group": "請求書", "field": "請求番号", "value": "INV-2026-001"},
        {"group": "請求書", "field": "取引先", "value": "サンプル商事"},
    ]
    total = 0
    for name, qty, price in rows:
        amount = int(qty) * int(price)
        total += amount
        items.append({"group": name, "field": "数量", "value": qty})
        items.append({"group": name, "field": "単価", "value": price})
        items.append({"group": name, "field": "金額", "value": str(amount)})
    items.append({"group": "合計", "field": "合計", "value": str(total)})
    return items


# ---------------------------------------------------------------- session

def session_dict(items, inputs, lang="ja", source_name=""):
    return {"version": 1, "lang": lang, "source_name": source_name,
            "items": items, "inputs": list(inputs)}


def session_from_dict(d):
    items = [{"group": str(i.get("group", "")), "field": str(i.get("field", "")),
              "value": str(i.get("value", ""))} for i in d.get("items", [])]
    inputs = [str(x) for x in d.get("inputs", [])]
    inputs += [""] * (len(items) - len(inputs))
    return items, inputs[:len(items)], d.get("lang", "ja"), d.get("source_name", "")

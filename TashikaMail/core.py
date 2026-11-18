# -*- coding: utf-8 -*-
"""Pre-send checker core: extraction + file readers.

Pure logic, no Qt imports, so it can be unit-tested anywhere.

Design rules (fixed by the user):
- The app NEVER sends mail. It only checks; the human decides and sends
  from their own mail software.
- NO fuzzy / similarity matching. Comparisons are exact after a
  deterministic normalization, or arithmetic.
- Anything that could not be read is reported honestly as
  "needs confirmation" (yellow), never as OK (green).
"""
import datetime
import email
import email.policy
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

GREEN, YELLOW, RED = "green", "yellow", "red"
LEVEL_ORDER = {GREEN: 0, YELLOW: 1, RED: 2}


def worst(*levels):
    if not levels:
        return GREEN
    return max(levels, key=lambda lv: LEVEL_ORDER[lv])


# ---------------------------------------------------------------------------
# normalization helpers
# ---------------------------------------------------------------------------

def to_half(text):
    """Fullwidth digits/punct -> halfwidth, halfwidth kana -> fullwidth."""
    if text is None:
        return ""
    return unicodedata.normalize("NFKC", str(text))


def parse_number(text):
    try:
        return Decimal(str(text).replace(",", "").replace(" ", "").strip())
    except (InvalidOperation, ValueError):
        return None


def fmt_money(value):
    if value is None:
        return "-"
    if value == value.to_integral_value():
        return f"{int(value):,}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# amounts
# ---------------------------------------------------------------------------

@dataclass
class Amount:
    value: Decimal
    currency: str          # JPY / USD / EUR / GBP / KRW / "" (unspecified)
    kind: str              # total / subtotal / tax / plain
    raw: str
    context: str


_TOTAL_WORDS = ("合計", "総計", "請求金額", "請求額", "お支払", "支払金額",
                "税込", "grand total", "total", "amount due", "total due",
                "balance due", "summe", "gesamtbetrag", "montant",
                "importe", "totale", "toplam", "합계", "总计", "총액")
_SUBTOTAL_WORDS = ("小計", "subtotal", "sub-total", "zwischensumme",
                   "소계", "小计")
_TAX_WORDS = ("消費税", "税額", "税金", "tax", "vat", "mwst", "부가세",
              "税额")


def _kind_from(text):
    low = text.lower()
    # subtotal first: the word "subtotal" itself contains "total"
    for w in _SUBTOTAL_WORDS:
        if w in low:
            return "subtotal"
    for w in _TOTAL_WORDS:
        if w in low:
            return "total"
    for w in _TAX_WORDS:
        if w in low:
            return "tax"
    return None


def _amount_kind(context):
    # The label normally sits on the same line, before the amount.
    line = context.replace("\r", "").split("\n")[-1]
    return _kind_from(line) or _kind_from(context) or "plain"


_AMOUNT_PATTERNS = [
    (r"[¥￥]\s*([0-9][0-9,]*\.?[0-9]*)", "JPY", 1),
    (r"([0-9][0-9,]*\.?[0-9]*)\s*(?:円|JPY)", "JPY", 1),
    (r"([0-9][0-9,]*\.?[0-9]*)\s*万\s*(?:円|JPY)", "JPY_MAN", 1),
    (r"\$\s*([0-9][0-9,]*\.?[0-9]*)", "USD", 1),
    (r"([0-9][0-9,]*\.?[0-9]*)\s*(?:USD|dollars?)", "USD", 1),
    (r"€\s*([0-9][0-9,]*\.?[0-9]*)", "EUR", 1),
    (r"([0-9][0-9,]*\.?[0-9]*)\s*(?:EUR|euros?)", "EUR", 1),
    (r"£\s*([0-9][0-9,]*\.?[0-9]*)", "GBP", 1),
    (r"([0-9][0-9,]*\.?[0-9]*)\s*(?:GBP|pounds?)", "GBP", 1),
    (r"₩\s*([0-9][0-9,]*)", "KRW", 1),
    (r"([0-9][0-9,]*)\s*(?:ウォン|KRW|원)", "KRW", 1),
]


def extract_amounts(text):
    """Extract amounts with currency + label kind. Overlaps de-duplicated."""
    text = to_half(text or "")
    found = []
    for pattern, currency, grp in _AMOUNT_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            num = parse_number(m.group(grp))
            if num is None:
                continue
            cur = currency
            if currency == "JPY_MAN":
                num = num * Decimal(10000)
                cur = "JPY"
            context = text[max(0, m.start() - 30):m.start()]
            found.append((m.start(), m.end(), Amount(
                value=num, currency=cur, kind=_amount_kind(context),
                raw=m.group(0), context=context.strip())))
    found.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    out, last_end = [], -1
    for start, end, amt in found:
        if start < last_end:
            continue
        out.append(amt)
        last_end = end
    return out


# ---------------------------------------------------------------------------
# dates
# ---------------------------------------------------------------------------

@dataclass
class DateHit:
    day: datetime.date
    kind: str              # deadline / validity / generic
    raw: str


_MONTHS = {name: i + 1 for i, name in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}
_MONTHS.update({name[:3]: num for name, num in list(_MONTHS.items())})
_MONTHS["sept"] = 9


def _date_kind(context):
    low = context.lower()
    if "有効" in context or "valid" in low:
        return "validity"
    if ("支払" in context or "pay" in low or "due" in low
            or "期限" in context or "fäll" in low or "vencimiento" in low
            or "scadenza" in low or "납기" in context or "到期" in context):
        return "deadline"
    return "generic"


def _safe_date(y, m, d):
    try:
        return datetime.date(int(y), int(m), int(d))
    except ValueError:
        return None


def extract_dates(text):
    text = to_half(text or "")
    hits, spans = [], []

    def add(day, start, end, raw):
        if day is None:
            return
        for s, e in spans:
            if start < e and end > s:
                return
        spans.append((start, end))
        ctx = text[max(0, start - 24):start]
        hits.append(DateHit(day=day, kind=_date_kind(ctx), raw=raw))

    for m in re.finditer(r"(20\d{2})[/\-.](\d{1,2})[/\-.](\d{1,2})", text):
        add(_safe_date(*m.groups()), m.start(), m.end(), m.group(0))
    for m in re.finditer(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", text):
        add(_safe_date(*m.groups()), m.start(), m.end(), m.group(0))
    wareki = {"令和": 2018, "平成": 1988, "昭和": 1925}
    for m in re.finditer(r"(令和|平成|昭和)(元|\d{1,2})年(\d{1,2})月(\d{1,2})日",
                         text):
        era, y, mo, d = m.groups()
        year = wareki[era] + (1 if y == "元" else int(y))
        add(_safe_date(year, mo, d), m.start(), m.end(), m.group(0))
    mon = (r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
           r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
           r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)")
    for m in re.finditer(rf"(\d{{1,2}})\s+{mon}\s*,?\s+(20\d{{2}})",
                         text, re.IGNORECASE):
        d, mname, y = m.groups()
        add(_safe_date(y, _MONTHS[mname.lower()], d),
            m.start(), m.end(), m.group(0))
    for m in re.finditer(
            rf"{mon}\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s+(20\d{{2}})",
            text, re.IGNORECASE):
        mname, d, y = m.groups()
        add(_safe_date(y, _MONTHS[mname.lower()], d),
            m.start(), m.end(), m.group(0))
    hits.sort(key=lambda h: h.day)
    return hits


# ---------------------------------------------------------------------------
# company names
# ---------------------------------------------------------------------------

_LEGAL_JA = ("株式会社", "有限会社", "合同会社", "合資会社", "合名会社")
_LEGAL_LATIN = ("inc", "ltd", "corp", "corporation", "gmbh", "llc", "llp",
                "company", "limited", "co", "sa", "sarl", "bv", "nv", "ag",
                "srl", "spa", "pty")
_NAME_STOP_CHARS = " \t\r\n、。,.，：:；;（）()［］[]「」【】<>/\\|　"


def _clean_company_core(core):
    core = to_half(core or "").strip(_NAME_STOP_CHARS)
    for suffix in ("御中", "様", "殿"):
        if core.endswith(suffix):
            core = core[:-len(suffix)]
    return core.strip(_NAME_STOP_CHARS)


def normalize_company(name):
    """Deterministic normalization: strip legal forms, width/case/punct."""
    s = to_half(name or "")
    for legal in _LEGAL_JA:
        s = s.replace(legal, "")
    s = s.replace("(株)", "").replace("(有)", "")
    s = unicodedata.normalize("NFKC", s).lower()
    tokens = [t for t in re.split(r"[\s\.,&\-_/]+", s)
              if t and t not in _LEGAL_LATIN]
    return "".join(tokens)


def extract_companies(text):
    """Return {normalized_name: raw_form}. Legal forms are stripped."""
    text = to_half(text or "")
    out = {}

    def add(core):
        core = _clean_company_core(core)
        if len(core) < 2:
            return
        if not re.search(r"[A-Za-z぀-ヿ㐀-鿿Ѐ-ӿ]", core):
            return  # pure numbers / punctuation are not company names
        norm = normalize_company(core)
        if len(norm) >= 2:
            out.setdefault(norm, core)

    for legal in _LEGAL_JA:
        for m in re.finditer(re.escape(legal)
                             + r"\s*([^\s、。,.，：:（）()]{2,20})", text):
            add(m.group(1))
        for m in re.finditer(r"([^\s、。,.，：:（）()]{2,20}?)\s*"
                             + re.escape(legal), text):
            add(m.group(1))
    for m in re.finditer(r"\(株\)\s*([^\s、。,.，：:（）()]{2,20})", text):
        add(m.group(1))
    for m in re.finditer(r"([^\s、。,.，：:（）()]{2,20})\s*\(株\)", text):
        add(m.group(1))
    latin = (r"([A-Z][A-Za-z0-9&\-\.]*(?:\s+[A-Z][A-Za-z0-9&\-\.]*){0,3}?)\s+"
             r"(?:Inc\.?|Ltd\.?|Corp\.?|Corporation|GmbH|S\.A\.|LLC|"
             r"Limited|Company)")
    for m in re.finditer(latin, text):
        add(m.group(1))
    for m in re.finditer(
            r"([A-Z][A-Za-z0-9&\-\.]*(?:\s+[A-Z][A-Za-z0-9&\-\.]*){0,3}?)"
            r"\s+Co\.,?\s*Ltd\.?", text):
        add(m.group(1))
    return out


def company_tokens(norm_name):
    """Latin word tokens of a normalized company name (domain checks)."""
    if not norm_name or not re.search(r"[a-z]", norm_name):
        return set()
    if re.search(r"[぀-ヿ㐀-鿿]", norm_name):
        return set()
    return {t for t in re.split(r"[^a-z0-9]+", norm_name) if len(t) >= 3}


# ---------------------------------------------------------------------------
# document numbers
# ---------------------------------------------------------------------------

_DOC_LABEL = (r"(?:請求書番号|請求番号|見積書番号|見積番号|注文番号|発注番号|"
              r"文書番号|伝票番号|invoice\s*(?:no\.?|number|#)|"
              r"estimate\s*(?:no\.?|number|#)|quotation\s*(?:no\.?|number|#)|"
              r"order\s*(?:no\.?|number|#)|po\s*(?:no\.?|number|#)|"
              r"doc(?:ument)?\s*(?:no\.?|number)|no\.|番号|номер|№|"
              r"청구번호|견적번호|发票号|编号)")


def normalize_docnum(token):
    return re.sub(r"[\s\-_]", "", to_half(token or "")).upper()


def extract_doc_numbers(text):
    text = to_half(text or "")
    out = {}
    for m in re.finditer(_DOC_LABEL
                         + r"\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9\-_]{2,})",
                         text, flags=re.IGNORECASE):
        token = m.group(1)
        if token.isdigit() and len(token) < 4:
            continue
        out.setdefault(normalize_docnum(token), token)
    for m in re.finditer(r"\b(INV|EST|QT|QUO|PO|ORD|BILL)-?(\d{3,})\b",
                         text, flags=re.IGNORECASE):
        out.setdefault(normalize_docnum(m.group(0)), m.group(0))
    return out


# ---------------------------------------------------------------------------
# OCR (Tesseract, bundled - same approach as TranscribeGuard)
#
# Resolution order for the tesseract executable:
#   1. environment override TASHIKAMAIL_TESSERACT_CMD (or ..._TESSERACT)
#   2. bundled copy: <base>/tesseract/tesseract.exe, where <base> is the
#      executable's folder when frozen, else this file's folder
#   3. system PATH ("tesseract")
# On macOS (darwin) the bundled copy is a Windows binary and can never
# run, so step 2 is replaced by the Homebrew prefixes
# (/opt/homebrew/bin, /usr/local/bin) - checked explicitly because
# Finder-launched apps do not inherit the shell PATH - and step 3 is the
# PATH fallback. The bundled tessdata (.traineddata files are portable
# data) is still used on macOS when present next to the app.
# Tessdata mirrors it: TASHIKAMAIL_TESSDATA_DIR override, then
# <base>/tesseract/tessdata, then <base>/tessdata, else tesseract's default.
# The bundled copy is Tesseract v5.5.3 + tessdata_fast for the 13 UI
# languages, copied from the proven TranscribeGuard bundle. OCR can
# misread - results read through OCR are flagged (Attachment.via_ocr)
# and the UI shows a caution row asking the user to compare numbers
# against the original document.
# ---------------------------------------------------------------------------

_TESS_ENV_VARS = ("TASHIKAMAIL_TESSERACT_CMD", "TASHIKAMAIL_TESSERACT")

UI_TO_TESS = {
    "ja": "jpn", "en": "eng", "es": "spa", "zh_CN": "chi_sim", "fr": "fra",
    "de": "deu", "pt": "por", "ru": "rus", "it": "ita", "tr": "tur",
    "ar": "ara", "id": "ind", "ko": "kor",
}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif",
              ".webp"}


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


# Homebrew prefixes on macOS (Apple Silicon, then Intel).
_HOMEBREW_TESSERACT = ("/opt/homebrew/bin/tesseract",
                       "/usr/local/bin/tesseract")


def tesseract_candidates(env=None, frozen=None, exe_dir=None, app_dir=None):
    env = os.environ if env is None else env
    cands = []
    for var in _TESS_ENV_VARS:
        if env.get(var):
            cands.append(env[var])
            break
    if sys.platform == "darwin":
        # macOS: the bundled copy is a Windows binary (tesseract.exe)
        # and cannot run here, so it is not a candidate. Use the
        # Homebrew locations instead; find_tesseract() then falls back
        # to the PATH. Windows/Linux resolution below is unchanged.
        cands.extend(_HOMEBREW_TESSERACT)
        return cands
    for base in _base_dirs(frozen, exe_dir, app_dir):
        cands.append(os.path.join(base, "tesseract", "tesseract.exe"))
        cands.append(os.path.join(base, "tesseract", "tesseract"))
    return cands


def find_tesseract(env=None, frozen=None, exe_dir=None, app_dir=None,
                   which=None):
    """Path of the tesseract executable to use, or None if not found."""
    which = shutil.which if which is None else which
    for cand in tesseract_candidates(env, frozen, exe_dir, app_dir):
        if cand and os.path.isfile(cand):
            return cand
    return which("tesseract") or which("tesseract.exe")


def tessdata_candidates(env=None, frozen=None, exe_dir=None, app_dir=None):
    env = os.environ if env is None else env
    cands = []
    if env.get("TASHIKAMAIL_TESSDATA_DIR"):
        cands.append(env["TASHIKAMAIL_TESSDATA_DIR"])
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
    kwargs = {"capture_output": True, "timeout": 300}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(cmd, **kwargs)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[:300])
    return proc.stdout.decode("utf-8", "replace")


def ocr_image_file(path, ui_lang="ja"):
    """OCR one image file and return the recognized text ('' if none).

    Returns '' (never raises) when tesseract is unavailable, the image
    cannot be opened, or nothing could be read - the caller reports the
    attachment honestly as unreadable in that case.
    """
    exe = find_tesseract()
    if exe is None:
        return ""
    try:
        from PIL import Image
        img = Image.open(path)
        img_format = (img.format or "").upper()
        img.load()
    except Exception:
        return ""
    tessdata_dir = find_tessdata_dir()
    tmp = None
    try:
        image_path = path
        needs_convert = img_format not in ("PNG", "JPEG", "TIFF", "BMP")
        small = max(img.size) < 1200
        if needs_convert or small:
            work = img.convert("RGB")
            if small:
                work = work.resize((work.width * 2, work.height * 2),
                                   Image.LANCZOS)
            fd, tmp = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            work.save(tmp)
            image_path = tmp
        lang_options = []
        for langs in (ocr_lang_string(ui_lang, tessdata_dir),
                      "jpn+eng", "eng"):
            if langs and langs not in lang_options:
                lang_options.append(langs)
        for langs in lang_options:
            try:
                text = _run_tesseract(exe, image_path, langs, tessdata_dir)
            except Exception:
                text = ""
            if text.strip():
                return text
        return ""
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# file readers
# ---------------------------------------------------------------------------

@dataclass
class Attachment:
    path: str
    name: str
    text: str = ""
    readable: bool = False
    error: str = ""
    mtime: float = 0.0
    via_ocr: bool = False      # text was obtained through OCR
    ocr_pages: int = 0         # PDF pages that went through OCR

    @property
    def amounts(self):
        return extract_amounts(self.text)

    @property
    def dates(self):
        return extract_dates(self.text)

    @property
    def companies(self):
        return extract_companies(self.text)

    @property
    def doc_numbers(self):
        return extract_doc_numbers(self.text)


def _decode_bytes(data):
    for enc in ("utf-8-sig", "shift_jis", "cp1252"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _read_pdf(path, ui_lang="ja", progress=None):
    """Return (text, ocr_pages) for a PDF.

    Pages with a text layer are read as text. Pages without one (scanned
    pages) are rendered to images with PyMuPDF and read through OCR, so
    mixed PDFs work page by page. ocr_pages counts the pages that went
    through OCR. When neither a reader nor OCR is available the text is
    simply empty and the attachment is reported as unreadable.
    """
    page_texts = []
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        for page in reader.pages:
            try:
                page_texts.append(page.extract_text() or "")
            except Exception:
                page_texts.append("")
    except Exception:
        page_texts = []
    if not page_texts:
        try:
            import fitz
            doc = fitz.open(path)
            page_texts = [(page.get_text() or "") for page in doc]
            doc.close()
        except Exception:
            page_texts = []
    ocr_pages = 0
    empty_pages = [i for i, t in enumerate(page_texts) if not t.strip()]
    if empty_pages and ocr_available():
        try:
            import fitz
            doc = fitz.open(path)
        except Exception:
            doc = None
        if doc is not None:
            try:
                for i in empty_pages:
                    if progress:
                        progress(i + 1, len(page_texts))
                    tmp = None
                    try:
                        pix = doc[i].get_pixmap(dpi=300)
                        fd, tmp = tempfile.mkstemp(suffix=".png")
                        os.close(fd)
                        pix.save(tmp)
                        text = ocr_image_file(tmp, ui_lang)
                    except Exception:
                        text = ""
                    finally:
                        if tmp:
                            try:
                                os.remove(tmp)
                            except OSError:
                                pass
                    if text.strip():
                        page_texts[i] = text
                        ocr_pages += 1
            finally:
                doc.close()
    parts = []
    for i, t in enumerate(page_texts, 1):
        if t.strip():
            parts.append(f"[p.{i}] {t}")
    return "\n".join(parts), ocr_pages


def _read_xlsx(path):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        parts = []
        for ws in wb.worksheets:
            cells = []
            for row in ws.iter_rows(values_only=True):
                for v in row:
                    if v is None:
                        continue
                    if isinstance(v, (datetime.datetime, datetime.date)):
                        cells.append(v.strftime("%Y/%m/%d"))
                    else:
                        cells.append(str(v))
            if cells:
                parts.append(f"[sheet:{ws.title}] " + " ".join(cells))
        wb.close()
        return "\n".join(parts)
    except ImportError:
        return _read_xlsx_stdlib(path)


def _read_xlsx_stdlib(path):
    import xml.etree.ElementTree as ET
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    mtag = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    parts = []
    with zipfile.ZipFile(path) as zf:
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", ns):
                shared.append("".join(t.text or ""
                                      for t in si.iter(mtag + "t")))
        for name in sorted(zf.namelist()):
            if re.match(r"xl/worksheets/sheet\d+\.xml", name):
                root = ET.fromstring(zf.read(name))
                cells = []
                for c in root.iter(mtag + "c"):
                    v = c.find("m:v", ns)
                    if v is None or v.text is None:
                        continue
                    if c.get("t") == "s":
                        try:
                            cells.append(shared[int(v.text)])
                            continue
                        except (ValueError, IndexError):
                            pass
                    cells.append(v.text)
                if cells:
                    parts.append(" ".join(cells))
    return "\n".join(parts)


def _read_docx(path):
    import xml.etree.ElementTree as ET
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    paras = []
    for p in root.iter(w + "p"):
        text = "".join(t.text or "" for t in p.iter(w + "t"))
        if text.strip():
            paras.append(text)
    return "\n".join(paras)


def read_attachment(path, name=None, ui_lang="ja", progress=None):
    name = name or os.path.basename(path)
    att = Attachment(path=path, name=name)
    try:
        att.mtime = os.path.getmtime(path)
    except OSError:
        att.mtime = 0.0
    ext = os.path.splitext(name)[1].lower()
    try:
        if ext == ".pdf":
            att.text, att.ocr_pages = _read_pdf(path, ui_lang, progress)
            att.via_ocr = att.ocr_pages > 0
        elif ext in IMAGE_EXTS:
            if progress:
                progress(1, 1)
            att.text = ocr_image_file(path, ui_lang)
            att.via_ocr = bool(att.text.strip())
        elif ext == ".xlsx":
            att.text = _read_xlsx(path)
        elif ext == ".docx":
            att.text = _read_docx(path)
        elif ext in (".txt", ".csv", ".tsv", ".md"):
            with open(path, "rb") as fh:
                att.text = _decode_bytes(fh.read())
        elif ext == ".eml":
            data = parse_eml(path, keep_attachments=False)
            att.text = (data.get("subject", "") + "\n"
                        + data.get("body", ""))
        else:
            att.text = ""
            att.error = "unsupported"
    except Exception as exc:
        att.text = ""
        att.error = str(exc)
    att.readable = bool(att.text and att.text.strip())
    if not att.readable and not att.error:
        att.error = "no_text"
    return att


# ---------------------------------------------------------------------------
# .eml decomposition
# ---------------------------------------------------------------------------

def parse_eml(path, keep_attachments=True, out_dir=None):
    """Split an .eml into To / Cc / Subject / body / attachments (files)."""
    with open(path, "rb") as fh:
        msg = email.message_from_binary_file(fh, policy=email.policy.default)
    to = str(msg.get("To", "") or "")
    cc = str(msg.get("Cc", "") or "")
    subject = str(msg.get("Subject", "") or "")
    body_text = ""
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", "") or "")
            filename = part.get_filename()
            if filename:
                if keep_attachments:
                    payload = part.get_payload(decode=True) or b""
                    target_dir = out_dir or os.path.join(
                        os.path.dirname(os.path.abspath(path)), "_eml_parts")
                    os.makedirs(target_dir, exist_ok=True)
                    safe = os.path.basename(str(filename))
                    dest = os.path.join(target_dir, safe)
                    base, ext = os.path.splitext(dest)
                    n = 2
                    while os.path.exists(dest):
                        dest = f"{base}_{n}{ext}"
                        n += 1
                    with open(dest, "wb") as out:
                        out.write(payload)
                    attachments.append({"name": safe, "path": dest})
                continue
            if ctype == "text/plain" and "attachment" not in disp:
                try:
                    body_text += part.get_content()
                except Exception:
                    payload = part.get_payload(decode=True) or b""
                    body_text += _decode_bytes(payload)
            elif ctype == "text/html" and not body_text.strip():
                try:
                    html = part.get_content()
                except Exception:
                    html = _decode_bytes(part.get_payload(decode=True) or b"")
                body_text += re.sub(r"<[^>]+>", " ", html)
    else:
        try:
            body_text = msg.get_content()
        except Exception:
            body_text = _decode_bytes(msg.get_payload(decode=True) or b"")
    recipients = []
    for field_value in (to, cc):
        recipients += [a.strip() for a in re.split(r"[,;]", field_value)
                       if a.strip()]
    return {"to": to, "cc": cc, "recipients": recipients,
            "subject": subject, "body": body_text.strip(),
            "attachments": attachments}

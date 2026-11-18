# -*- coding: utf-8 -*-
"""Core-system integrations — ContextStruct v2 (user point I).

Four delivery methods, all built into the app. HONEST SCOPE, shown in the
UI and README: the mechanisms live in the app, but using one requires
per-system information supplied by the user (CSS selectors, the target
system's import spec, DB connection details and that company's
permission). Nothing here guesses a destination.

Method 1  RPA keyboard auto-entry: types confirmed values into whatever
          application the user focused, value -> Tab -> value -> ...
          Windows uses ctypes SendInput; other platforms go through the
          abstract KeyboardSender (unit tests use the mock). Safety:
          3-second countdown (GUI), Esc aborts immediately, per-field
          interval is configurable. The final "register" click is a
          SEPARATE opt-in: it only clicks coordinates the user recorded
          by clicking the real button; never a guessed position.
Method 2  Web-form DOM: field -> CSS selector mapping. Generates a
          bookmarklet (JavaScript string) that fills the form in the
          user's browser; optionally drives a real browser via selenium
          when importable (no driver bundled).
Method 3  Import file: CSV/TSV/Excel with encoding (UTF-8 / Shift-JIS),
          newline (CRLF/LF), header on/off, date format, column order
          and a dated filename pattern. Also usable as the unattended
          automation output destination.
Method 4  Direct DB write: sqlite (stdlib) or ODBC (pyodbc, lazy).
          Dry-run by default: builds and previews the INSERT statements
          without writing. Real writes require the profile's explicit
          "enable DB write" toggle, run in one transaction, and are
          recorded in the audit log by the caller.
"""
import os, re, csv, io, json, sys, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from context_core import get_app_dir

METHODS = ("rpa", "webform", "file", "db")


class IntegrationUnavailable(Exception):
    pass


# ------------------------------------------------------------- profiles ----
class IntegrationProfile:
    def __init__(self, name="", method="file", config=None):
        self.name = name
        self.method = method if method in METHODS else "file"
        self.config = dict(config or {})

    def to_dict(self):
        return {"name": self.name, "method": self.method, "config": self.config}

    @staticmethod
    def from_dict(d):
        return IntegrationProfile(d.get("name", ""), d.get("method", "file"), d.get("config") or {})


def integrations_path(base_dir=None):
    return os.path.join(base_dir or get_app_dir(), "integrations.json")


def load_integrations(base_dir=None):
    p = integrations_path(base_dir)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return [IntegrationProfile.from_dict(d) for d in json.load(f)]
        except Exception:
            pass
    return []


def save_integrations(profiles, base_dir=None):
    p = integrations_path(base_dir)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump([x.to_dict() for x in profiles], f, ensure_ascii=False, indent=2)
    return p


# ------------------------------------------------- method 1: RPA keyboard ----
class KeyboardSender:
    """Abstract keyboard/mouse sender (the unit-testable layer)."""
    def type_text(self, text):
        raise NotImplementedError
    def press_tab(self):
        raise NotImplementedError
    def click(self, x, y):
        raise NotImplementedError


class MockKeyboardSender(KeyboardSender):
    def __init__(self):
        self.events = []
    def type_text(self, text):
        self.events.append(("type", text))
    def press_tab(self):
        self.events.append(("tab",))
    def click(self, x, y):
        self.events.append(("click", x, y))


class WinKeyboardSender(KeyboardSender):
    """Windows SendInput sender (ctypes). Only constructed on win32."""
    def __init__(self):
        import ctypes
        self.ctypes = ctypes
        self.user32 = ctypes.windll.user32
        KEYEVENTF_UNICODE = 0x0004
        self._KEYEVENTF_UNICODE = KEYEVENTF_UNICODE
        self._KEYEVENTF_KEYUP = 0x0002
        self._INPUT_KEYBOARD = 1
        self._INPUT_MOUSE = 0
        self._MOUSEEVENTF_LEFTDOWN = 0x0002
        self._MOUSEEVENTF_LEFTUP = 0x0004
        self._MOUSEEVENTF_ABSOLUTE = 0x8000
        self._MOUSEEVENTF_MOVE = 0x0001

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                        ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                        ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
        class _U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]
        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("u", _U)]
        self._INPUT, self._KEYBDINPUT, self._MOUSEINPUT, self._U = INPUT, KEYBDINPUT, MOUSEINPUT, _U

    def _send(self, inp):
        self.user32.SendInput(1, self.ctypes.byref(inp), self.ctypes.sizeof(inp))

    def _key(self, vk=0, scan=0, flags=0):
        inp = self._INPUT()
        inp.type = self._INPUT_KEYBOARD
        inp.u.ki = self._KEYBDINPUT(vk, scan, flags, 0, None)
        self._send(inp)

    def type_text(self, text):
        for ch in str(text):
            code = ord(ch)
            self._key(0, code, self._KEYEVENTF_UNICODE)
            self._key(0, code, self._KEYEVENTF_UNICODE | self._KEYEVENTF_KEYUP)

    def press_tab(self):
        self._key(0x09, 0, 0)
        self._key(0x09, 0, self._KEYEVENTF_KEYUP)

    def click(self, x, y):
        sw = self.user32.GetSystemMetrics(0) or 1920
        sh = self.user32.GetSystemMetrics(1) or 1080
        inp = self._INPUT()
        inp.type = self._INPUT_MOUSE
        inp.u.mi = self._MOUSEINPUT(int(x * 65535 / max(1, sw - 1)), int(y * 65535 / max(1, sh - 1)),
                                    0, self._MOUSEEVENTF_MOVE | self._MOUSEEVENTF_ABSOLUTE, 0, None)
        self._send(inp)
        for fl in (self._MOUSEEVENTF_LEFTDOWN, self._MOUSEEVENTF_LEFTUP):
            inp2 = self._INPUT()
            inp2.type = self._INPUT_MOUSE
            inp2.u.mi = self._MOUSEINPUT(0, 0, 0, fl, 0, None)
            self._send(inp2)


def make_sender():
    if sys.platform.startswith("win"):
        return WinKeyboardSender()
    raise IntegrationUnavailable("RPA keyboard sending is only available on Windows")


def esc_pressed():
    """True while Esc is held (Windows). Always False elsewhere."""
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)
    except Exception:
        return False


def rpa_type_values(values, sender, interval_ms=150, should_abort=None, sleep_fn=None):
    """Type values in order: value, Tab, value, ... (no trailing Tab).
    Aborts BEFORE the next field when should_abort() is true.
    Returns {'typed': n, 'aborted': bool}."""
    import time as _time
    sleep_fn = sleep_fn or (lambda ms: _time.sleep(ms / 1000.0))
    typed = 0
    for i, v in enumerate(values):
        if should_abort and should_abort():
            return {"typed": typed, "aborted": True}
        sender.type_text("" if v is None else str(v))
        typed += 1
        if i < len(values) - 1:
            sender.press_tab()
        if interval_ms:
            sleep_fn(interval_ms)
    return {"typed": typed, "aborted": False}


def rpa_finish_click(cfg, sender):
    """The optional final 'register' click. Fires ONLY when the profile has
    it enabled AND coordinates were recorded by the user. Never guesses."""
    if not cfg.get("rpa_click_enabled"):
        return False
    x, y = cfg.get("rpa_click_x"), cfg.get("rpa_click_y")
    if x is None or y is None:
        return False
    sender.click(int(x), int(y))
    return True


# ------------------------------------------------- method 2: web form DOM ----
def _js_str(s):
    return json.dumps("" if s is None else str(s), ensure_ascii=True)


def generate_bookmarklet(mapping, row):
    """mapping: {field_column: css_selector}; row: {field_column: value}.
    Returns a javascript: bookmarklet that fills the mapped form fields and
    fires input/change events so frameworks notice the values."""
    lines = ["(function(){", "function setV(sel,val){var el=document.querySelector(sel);if(!el)return;var d=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el),'value');if(d&&d.set){d.set.call(el,val);}else{el.value=val;}el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}"]
    for col, sel in mapping.items():
        if not sel:
            continue
        lines.append(f"setV({_js_str(sel)},{_js_str(row.get(col, ''))});")
    lines.append("})();")
    return "javascript:" + "".join(lines)


def fill_form_selenium(url, mapping, row, driver_factory=None):
    """Optional direct browser fill via selenium (lazy import; no driver is
    bundled). Raises IntegrationUnavailable when selenium is absent."""
    if driver_factory is None:
        try:
            from selenium import webdriver
        except Exception:
            raise IntegrationUnavailable("selenium is not installed; use the bookmarklet instead")
        driver_factory = webdriver.Chrome
    driver = driver_factory()
    try:
        driver.get(url)
        for col, sel in mapping.items():
            if not sel:
                continue
            el = driver.find_element("css selector", sel)
            el.clear()
            el.send_keys("" if row.get(col) is None else str(row.get(col)))
    finally:
        pass  # leave the browser open for the user to review/submit
    return driver


# ---------------------------------------------------- method 3: import file ----
def resolve_filename(pattern, profile_name="", when=None):
    when = when or datetime.datetime.now()
    name = (pattern or "export_{date}.csv")
    name = name.replace("{date}", when.strftime("%Y%m%d")).replace("{datetime}", when.strftime("%Y%m%d_%H%M%S"))
    name = name.replace("{profile}", re.sub(r"[^\w\-]", "_", profile_name or "data"))
    return name


def _format_dates(value, date_fmt):
    if not date_fmt or not value:
        return value
    s = str(value)
    try:
        dt = datetime.datetime.strptime(s, "%Y-%m-%d")
        return dt.strftime(date_fmt)
    except Exception:
        return value


def ordered_columns(cfg, profile_columns):
    order = cfg.get("column_order") or []
    cols = [c for c in order if c in profile_columns]
    cols += [c for c in profile_columns if c not in cols]
    return cols


def export_import_file(rows_dicts, profile_columns, cfg, out_path, append=False):
    """Write rows in the target system's import format.
    cfg: format(csv/tsv/xlsx), encoding(utf-8/shift_jis), newline(crlf/lf),
    header(bool), date_format(strftime or ''), column_order(list).
    For csv/tsv with append=True and an existing file, rows are appended
    without a header. Returns out_path."""
    fmt = (cfg.get("format") or "csv").lower()
    cols = ordered_columns(cfg, profile_columns)
    date_fmt = cfg.get("date_format") or ""
    data = [{c: _format_dates(r.get(c, ""), date_fmt) for c in cols} for r in rows_dicts]
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    if fmt == "xlsx":
        from openpyxl import Workbook, load_workbook
        if append and os.path.isfile(out_path):
            wb = load_workbook(out_path); ws = wb.active
        else:
            wb = Workbook(); ws = wb.active
            if cfg.get("header", True):
                ws.append(cols)
        for d in data:
            ws.append([d[c] for c in cols])
        wb.save(out_path)
        return out_path
    delim = "\t" if fmt == "tsv" else ","
    enc = "shift_jis" if (cfg.get("encoding") or "utf-8").lower().startswith("shift") else "utf-8"
    newline = "\r\n" if (cfg.get("newline") or "crlf").lower() == "crlf" else "\n"
    exists = append and os.path.isfile(out_path) and os.path.getsize(out_path) > 0
    mode = "a" if exists else "w"
    with io.open(out_path, mode, encoding=enc, newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=delim, lineterminator=newline)
        if not exists and cfg.get("header", True):
            w.writeheader()
        w.writerows(data)
    return out_path


# ------------------------------------------------------ method 4: direct DB ----
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check_ident(name, what="identifier"):
    if not _IDENT_RE.match(str(name or "")):
        raise ValueError(f"unsafe {what}: {name!r}")
    return str(name)


def build_insert(table, mapping, row):
    """Parameterized INSERT. mapping: {field_column: db_column}.
    Table/column identifiers are validated (they cannot be bound as
    parameters); values are always bound."""
    _check_ident(table, "table name")
    cols, params = [], []
    for field_col, db_col in mapping.items():
        if not db_col:
            continue
        cols.append(_check_ident(db_col, "column name"))
        params.append(row.get(field_col, ""))
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})"
    return sql, params


def db_preview(cfg, rows_dicts):
    mapping = cfg.get("column_mapping") or {}
    return [build_insert(cfg.get("table", ""), mapping, r) for r in rows_dicts]


def db_write(cfg, rows_dicts, force_dry_run=None):
    """Returns {'dry_run': bool, 'preview': [(sql, params)], 'written': n}.
    Dry-run unless the profile explicitly enables writes (cfg
    db_write_enabled) — force_dry_run overrides for tests/UI preview."""
    preview = db_preview(cfg, rows_dicts)
    enabled = bool(cfg.get("db_write_enabled", False))
    dry = (not enabled) if force_dry_run is None else bool(force_dry_run)
    if dry:
        return {"dry_run": True, "preview": preview, "written": 0}
    kind = (cfg.get("db_kind") or "sqlite").lower()
    conn_str = cfg.get("connection", "")
    written = 0
    if kind == "sqlite":
        import sqlite3
        conn = sqlite3.connect(conn_str)
        try:
            cur = conn.cursor()
            for sql, params in preview:
                cur.execute(sql, params)
                written += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    elif kind == "odbc":
        try:
            import pyodbc
        except Exception:
            raise IntegrationUnavailable("pyodbc is not installed; ODBC writes are unavailable")
        conn = pyodbc.connect(conn_str)
        try:
            cur = conn.cursor()
            for sql, params in preview:
                cur.execute(sql, params)
                written += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        raise ValueError(f"unknown db kind: {kind}")
    return {"dry_run": False, "preview": preview, "written": written}


# ============================================================ setup assist ====
# Added so non-technical users never have to hand-write technical settings:
# click-to-learn web mappings, import-spec inference from a sample file,
# profile export/import (one expert sets it up, everyone imports it), and a
# form-based DB connection assistant with a connection test.

def generate_learn_bookmarklet(field_names):
    """A bookmarklet that LEARNS the field->selector mapping by clicking.
    Run it on the target form: it asks, in order, 'click the input for
    <field>'; each click records a selector (id first, then name, then an
    nth-of-type path); at the end it returns the mapping as JSON (clipboard
    + prompt display) which the app imports back."""
    fields_js = json.dumps(list(field_names), ensure_ascii=True)
    js = []
    js.append("(function(){")
    js.append(f"var FIELDS={fields_js};var result={{}};var i=0;")
    js.append("function selOf(el){if(el.id){return '#'+el.id;}if(el.getAttribute('name')){return el.tagName.toLowerCase()+'[name=\"'+el.getAttribute('name')+'\"]';}var parts=[];var n=el;while(n&&n.nodeType===1&&n.tagName!=='BODY'){var ix=1;var s=n.previousElementSibling;while(s){if(s.tagName===n.tagName){ix++;}s=s.previousElementSibling;}parts.unshift(n.tagName.toLowerCase()+':nth-of-type('+ix+')');n=n.parentElement;}return parts.join(' > ');}")
    js.append("var bar=document.createElement('div');bar.style.cssText='position:fixed;top:0;left:0;right:0;z-index:999999;background:#1d46a8;color:#fff;font:16px sans-serif;padding:10px;text-align:center';document.body.appendChild(bar);")
    js.append("function done(){var j=JSON.stringify(result);bar.textContent='DONE';if(navigator.clipboard){navigator.clipboard.writeText(j);}window.prompt('Copy this mapping JSON and import it in ContextStruct:',j);document.removeEventListener('click',h,true);bar.remove();}")
    js.append("function h(e){e.preventDefault();e.stopPropagation();result[FIELDS[i]]=selOf(e.target);i++;if(i>=FIELDS.length){done();}else{bar.textContent=FIELDS[i];}}")
    js.append("if(FIELDS.length===0){return;}bar.textContent=FIELDS[0];document.addEventListener('click',h,true);")
    js.append("})();")
    return "javascript:" + "".join(js)


def parse_mapping_json(text):
    """Tolerant import of a mapping JSON produced by the learn bookmarklet
    (or a hand-shared profile snippet). Returns {field: selector} strings only."""
    if not text:
        return {}
    s = str(text)
    start, end = s.find("{"), s.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(s[start:end + 1])
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if v is not None and str(v) != ""}


def infer_import_spec(data):
    """Infer an import-file spec (method 3 draft) from sample bytes:
    encoding (UTF-8 tried first, then Shift-JIS), delimiter, newline,
    header presence and the column list. Returns a config draft dict."""
    if isinstance(data, (bytes, bytearray)):
        raw = bytes(data)
        text, enc = None, "utf-8"
        for cand_enc, label in (("utf-8-sig", "utf-8"), ("shift_jis", "shift_jis")):
            try:
                text = raw.decode(cand_enc)
                enc = label
                break
            except Exception:
                continue
        if text is None:
            text = raw.decode("utf-8", errors="ignore")
            enc = "utf-8"
    else:
        text, enc = str(data), "utf-8"
    newline = "crlf" if "\r\n" in text else "lf"
    lines = [ln for ln in text.splitlines() if ln.strip()][:6]
    sample = "\n".join(lines)
    delim = ","
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=",\t;").delimiter
    except Exception:
        counts = {d: sum(ln.count(d) for ln in lines) for d in (",", "\t", ";")}
        delim = max(counts, key=counts.get) if lines else ","
        if counts.get(delim, 0) == 0:
            delim = ","
    fmt = "tsv" if delim == "\t" else "csv"
    rows = []
    try:
        rows = list(csv.reader(io.StringIO(text), delimiter=delim))
        rows = [r for r in rows if any(c.strip() for c in r)][:4]
    except Exception:
        rows = []
    header = False
    columns = []
    if rows:
        first = [c.strip() for c in rows[0]]
        def _numeric(s):
            try:
                float(str(s).replace(",", ""))
                return True
            except Exception:
                return False
        first_textual = all((not _numeric(c)) and c != "" for c in first)
        second_differs = len(rows) < 2 or any(_numeric(c) for c in rows[1]) or rows[1] != rows[0]
        try:
            sniff_header = csv.Sniffer().has_header(sample)
        except Exception:
            sniff_header = False
        header = bool(first_textual and second_differs) or bool(sniff_header and first_textual)
        if header:
            columns = first
    return {"format": fmt, "encoding": enc, "newline": newline, "header": header,
            "delimiter": delim, "columns": columns,
            "column_order": columns}


def export_integration_profile(profile, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)
    return path


def import_integration_profiles(path):
    """Import one profile object or a list of them from a JSON file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    return [IntegrationProfile.from_dict(d) for d in data if isinstance(d, dict)]


# ------------------------------------------------------- DB assistant ----
def build_odbc_connection(server, database, driver="ODBC Driver 18 for SQL Server",
                          trusted=True, user="", password=""):
    parts = [f"DRIVER={{{driver}}}", f"SERVER={server}", f"DATABASE={database}"]
    if trusted:
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={user}")
        parts.append(f"PWD={password}")
    return ";".join(parts) + ";"


def _connect(cfg):
    kind = (cfg.get("db_kind") or "sqlite").lower()
    if kind == "sqlite":
        import sqlite3
        return sqlite3.connect(cfg.get("connection", ""))
    try:
        import pyodbc
    except Exception:
        raise IntegrationUnavailable("pyodbc is not installed; ODBC is unavailable")
    return pyodbc.connect(cfg.get("connection", ""))


def list_db_tables(cfg):
    conn = _connect(cfg)
    try:
        if (cfg.get("db_kind") or "sqlite").lower() == "sqlite":
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
            return [r[0] for r in rows]
        cur = conn.cursor()
        return [r.table_name for r in cur.tables(tableType="TABLE")]
    finally:
        conn.close()


def list_db_columns(cfg, table):
    _check_ident(table, "table name")
    conn = _connect(cfg)
    try:
        if (cfg.get("db_kind") or "sqlite").lower() == "sqlite":
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
            return [r[1] for r in rows]
        cur = conn.cursor()
        return [r.column_name for r in cur.columns(table=table)]
    finally:
        conn.close()


def test_connection(cfg):
    """Returns (ok, message, tables). Never raises."""
    try:
        tables = list_db_tables(cfg)
        return True, f"OK ({len(tables)} tables)", tables
    except Exception as e:
        return False, str(e), []

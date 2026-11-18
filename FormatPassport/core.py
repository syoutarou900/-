# -*- coding: utf-8 -*-
"""FormatPassport core: table IO, format analysis/conversion, FX.

Semi-auto rule: the engine prepares conversion proposals and flags anything
readable two ways into a review list. It never guesses an ambiguous value.
"""
import csv
import io
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from countries import BY_CODE, MINOR_UNITS

# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
_FW_TABLE = {ord("０") + i: ord("0") + i for i in range(10)}
_FW_TABLE.update({
    ord("．"): ".", ord("。"): ".", ord("，"): ",", ord("、"): ",",
    ord("－"): "-", ord("ー"): "-", ord("／"): "/", ord("："): ":",
    ord("　"): " ",
})
for i in range(26):
    _FW_TABLE[ord("Ａ") + i] = ord("A") + i
    _FW_TABLE[ord("ａ") + i] = ord("a") + i


def normalize_fullwidth(s):
    """Fullwidth digits/punct -> halfwidth (used in numeric/date contexts)."""
    return s.translate(_FW_TABLE)


def minor_unit(code):
    return MINOR_UNITS.get(code, 2)


# --------------------------------------------------------------------------
# Table IO
# --------------------------------------------------------------------------
class Table:
    def __init__(self, headers, rows, meta=None):
        self.headers = headers          # list[str]
        self.rows = rows                # list[list[str]]
        self.meta = meta or {}


def detect_encoding(raw):
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return "utf-16"
    for enc in ("utf-8", "shift_jis"):
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return "latin-1"


def detect_delimiter(text):
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        pass
    lines = [ln for ln in sample.splitlines() if ln.strip()][:10]
    best, best_score = ",", -1
    for cand in (",", ";", "\t", "|"):
        counts = [ln.count(cand) for ln in lines]
        if counts and min(counts) > 0:
            score = min(counts) * 100 - (max(counts) - min(counts))
            if score > best_score:
                best, best_score = cand, score
    return best


def parse_csv_text(text, delimiter=None):
    if delimiter is None:
        delimiter = detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [r for r in reader]
    if not rows:
        return Table([], []), delimiter
    headers = [h.strip() for h in rows[0]]
    body = []
    for r in rows[1:]:
        if len(r) < len(headers):
            r = r + [""] * (len(headers) - len(r))
        body.append(r[:len(headers)])
    return Table(headers, body), delimiter


def load_table(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook  # lazy: heavy import
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append(["" if c is None else
                         (c.isoformat() if isinstance(c, (date, datetime)) else str(c))
                         for c in row])
        wb.close()
        if not rows:
            return Table([], [], {"source_format": "xlsx"})
        headers = [h.strip() for h in rows[0]]
        body = []
        for r in rows[1:]:
            if len(r) < len(headers):
                r = r + [""] * (len(headers) - len(r))
            body.append(r[:len(headers)])
        return Table(headers, body, {"source_format": "xlsx"})
    with open(path, "rb") as fh:
        raw = fh.read()
    enc = detect_encoding(raw)
    text = raw.decode(enc)
    table, delim = parse_csv_text(text)
    table.meta = {"source_format": "csv", "encoding": enc, "delimiter": delim}
    return table


def table_to_csv_text(table, delimiter=",", encoding="utf-8-sig"):
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\r\n")
    writer.writerow(table.headers)
    writer.writerows(table.rows)
    text = buf.getvalue()
    if encoding == "shift_jis":
        return text.encode("shift_jis", errors="replace")
    if encoding == "utf-8":
        return text.encode("utf-8")
    return ("\ufeff" + text).encode("utf-8")  # utf-8-sig


def save_table_xlsx(table, path):
    from openpyxl import Workbook  # lazy
    wb = Workbook()
    ws = wb.active
    ws.append(table.headers)
    for r in table.rows:
        ws.append(r)
    wb.save(path)


def save_table_csv(table, path, delimiter=",", encoding="utf-8-sig"):
    data = table_to_csv_text(table, delimiter, encoding)
    with open(path, "wb") as fh:
        fh.write(data)


# --------------------------------------------------------------------------
# Wareki (Japanese era) conversion
# --------------------------------------------------------------------------
ERAS = [  # (kanji, letter, first Gregorian year of era year 1)
    ("令和", "R", 2019), ("平成", "H", 1989), ("昭和", "S", 1926),
    ("大正", "T", 1912), ("明治", "M", 1868),
]
_ERA_BY_KANJI = {k: (ltr, start) for k, ltr, start in ERAS}
_ERA_BY_LETTER = {ltr: (k, start) for k, ltr, start in ERAS}
_WAREKI_FULL = re.compile(
    r"^(令和|平成|昭和|大正|明治)(元|\d{1,2})年(\d{1,2})月(\d{1,2})日$")
_WAREKI_SHORT = re.compile(r"^([RHSTM])(\d{1,2})[./](\d{1,2})[./](\d{1,2})$", re.I)


def wareki_to_date(s):
    """Parse a wareki string to a date; None when not wareki/unparseable."""
    s = normalize_fullwidth(str(s).strip())
    m = _WAREKI_FULL.match(s)
    if m:
        era, y, mo, d = m.groups()
        _, start = _ERA_BY_KANJI[era]
        year = start + (1 if y == "元" else int(y)) - 1
        try:
            return date(year, int(mo), int(d))
        except ValueError:
            return None
    m = _WAREKI_SHORT.match(s.replace("-", ".").replace("/", "."))
    if m:
        ltr, y, mo, d = m.groups()
        _, start = _ERA_BY_LETTER[ltr.upper()]
        try:
            return date(start + int(y) - 1, int(mo), int(d))
        except ValueError:
            return None
    return None


def is_wareki(s):
    s = normalize_fullwidth(str(s).strip())
    return bool(_WAREKI_FULL.match(s) or
                _WAREKI_SHORT.match(s.replace("-", ".").replace("/", ".")))


def date_to_wareki(d, style="full"):
    for kanji, ltr, start in ERAS:
        if d.year >= start:
            ey = d.year - start + 1
            if style == "short":
                return "%s%d.%d.%d" % (ltr, ey, d.month, d.day)
            ys = "元" if ey == 1 else str(ey)
            return "%s%s年%d月%d日" % (kanji, ys, d.month, d.day)
    return None


# --------------------------------------------------------------------------
# Date parsing with ambiguity control
# --------------------------------------------------------------------------
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}
_DATE_SPLIT = re.compile(r"^(\d{1,4})\D(\d{1,2})(?:\D(\d{1,4}))?$")
_DATE_MONTHNAME = re.compile(
    r"^(\d{1,2})[ ./-]([A-Za-z]{3,9})[ ./-](\d{2,4})$")
_DATE_MONTHNAME2 = re.compile(
    r"^([A-Za-z]{3,9})[ ./-](\d{1,2})[ .,\/-]+(\d{2,4})$")


def _pivot_year(y):
    if y < 100:
        return 2000 + y if y <= 68 else 1900 + y
    return y


def _try_date(y, m, d):
    try:
        return date(y, m, d)
    except ValueError:
        return None


def classify_numeric_date(s):
    """Return info dict for a numeric date string (2 or 3 parts), or None.

    Keys: parts (a, b, c_or_None), year_pos ('first'/'last'/'none').
    """
    m = _DATE_SPLIT.match(s)
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    if m.group(3) is None:
        return {"parts": (a, b, None), "year_pos": "none"}
    c = int(m.group(3))
    if len(m.group(1)) == 4 or a > 31:
        year_pos = "first"
    else:
        year_pos = "last"
    return {"parts": (a, b, c), "year_pos": year_pos}


def parse_date_with_order(s, order):
    """Parse s assuming component order ('DMY','MDY','YMD'); date or None."""
    info = classify_numeric_date(s)
    if info:
        a, b, c = info["parts"]
        if info["year_pos"] == "first":
            y, m, d = a, b, c
        elif info["year_pos"] == "none":
            y = date.today().year
            if order == "DMY":
                d, m = a, b
            else:  # MDY, and YMD receivers read month/day too
                m, d = a, b
        elif order == "DMY":
            d, m, y = a, b, _pivot_year(c)
        elif order == "MDY":
            m, d, y = a, b, _pivot_year(c)
        else:  # YMD with year last is not a thing; treat as DMY fallback
            d, m, y = a, b, _pivot_year(c)
        return _try_date(y, m, d)
    m = _DATE_MONTHNAME.match(s)
    if m:
        d, mon, y = m.groups()
        mm = _MONTHS.get(mon[:3].lower())
        if mm:
            return _try_date(_pivot_year(int(y)), mm, int(d))
    m = _DATE_MONTHNAME2.match(s)
    if m:
        mon, d, y = m.groups()
        mm = _MONTHS.get(mon[:3].lower())
        if mm:
            return _try_date(_pivot_year(int(y)), mm, int(d))
    return None


def format_date_short(d, profile):
    """Two-component (month/day) rendering for yearless input dates."""
    sep = profile["date_sep"]
    if profile["date_order"] == "DMY":
        return "%02d%s%02d" % (d.day, sep, d.month)
    return "%02d%s%02d" % (d.month, sep, d.day)


def format_date(d, profile):
    order = profile["date_order"]
    sep = profile["date_sep"]
    if order == "DMY":
        return "%02d%s%02d%s%04d" % (d.day, sep, d.month, sep, d.year)
    if order == "MDY":
        return "%02d%s%02d%s%04d" % (d.month, sep, d.day, sep, d.year)
    return "%04d%s%02d%s%02d" % (d.year, sep, d.month, sep, d.day)


def analyze_date_column(values, sender_order):
    """Decide the proven order for a column of date strings.

    Returns (order_or_None, proven_reason). order None => undecidable per cell.
    """
    proofs = set()
    saw_numeric = False
    for v in values:
        info = classify_numeric_date(v)
        if not info:
            continue
        saw_numeric = True
        a, b, _c = info["parts"]
        if info["year_pos"] == "first":
            proofs.add("YMD")
        else:
            if a > 12 and b <= 12:
                proofs.add("DMY")
            elif b > 12 and a <= 12:
                proofs.add("MDY")
    if not saw_numeric:
        return sender_order, "no numeric dates"
    real = {p for p in proofs if p in ("DMY", "MDY")}
    if "YMD" in proofs and not real:
        return "YMD", "year-first values"
    if len(real) == 1:
        return real.pop(), "column evidence"
    if len(real) > 1:
        return None, "conflicting evidence"
    # No in-column evidence: the sender country's nominal order is NOT
    # trusted on its own (files routinely deviate from it — that is the
    # whole problem this app exists for). Dual-readable cells get flagged.
    return None, "no column evidence"


# --------------------------------------------------------------------------
# Number parsing with ambiguity control
# --------------------------------------------------------------------------
_CCY_TOKENS = [
    ("JPY", ("¥", "円", "JPY")), ("USD", ("$", "USD", "ドル")),
    ("EUR", ("€", "EUR")), ("GBP", ("£", "GBP")),
    ("CNY", ("元", "CNY")), ("KRW", ("₩", "KRW")),
]
_SPACE_CHARS = " \u00a0\u202f\u2009"


def _strip_currency(s):
    t = s
    found = None
    for code, toks in _CCY_TOKENS:
        for tok in toks:
            if tok and (t.startswith(tok) or t.endswith(tok)):
                t = t.replace(tok, "").strip()
                found = code
    return t, found


def parse_number(s, decimal_sep, thousands_sep, proof=None):
    """Parse a number string under one separator hypothesis.

    Returns (Decimal, info) or (None, info). info['ambiguous'] is True for
    the classic single-separator + exactly-3-trailing-digits shape, unless
    `proof` (dict: separator char -> 'decimal'|'thousands', derived from
    unambiguous values elsewhere in the column) settles that separator.
    """
    proof = proof or {}
    info = {"ambiguous": False, "currency": None}
    if s is None:
        return None, info
    t = normalize_fullwidth(str(s).strip())
    t, ccy = _strip_currency(t)
    info["currency"] = ccy
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg, t = True, t[1:-1]
    if t.startswith("-"):
        neg, t = True, t[1:]
    if t.endswith("%"):
        t = t[:-1]
    for ch in _SPACE_CHARS:
        t = t.replace(ch, "")
    t = t.replace("'", "")
    if not t or not re.fullmatch(r"[0-9.,]+", t):
        return None, info
    has_dot, has_comma = "." in t, "," in t
    try:
        if has_dot and has_comma:
            dec = "." if t.rfind(".") > t.rfind(",") else ","
            thou = "," if dec == "." else "."
            v = Decimal(t.replace(thou, "").replace(dec, "."))
        elif has_dot or has_comma:
            sep = "." if has_dot else ","
            parts = t.split(sep)
            if len(parts) > 2:
                if any(len(p) != 3 for p in parts[1:]):
                    return None, info
                v = Decimal("".join(parts))
            elif len(parts[1]) == 3 and len(parts[0]) <= 3 and parts[0] != "0":
                if proof.get(sep) == "thousands":
                    v = Decimal(parts[0] + parts[1])
                elif proof.get(sep) == "decimal":
                    v = Decimal(parts[0] + "." + parts[1])
                else:
                    info["ambiguous"] = True
                if info["ambiguous"]:
                    if sep == decimal_sep:
                        v = Decimal(parts[0] + "." + parts[1])
                        info["alt"] = Decimal(parts[0] + parts[1])
                    else:
                        v = Decimal(parts[0] + parts[1])
                        info["alt"] = Decimal(parts[0] + "." + parts[1])
            else:
                if sep == decimal_sep:
                    v = Decimal(parts[0] + "." + parts[1])
                elif sep == thousands_sep:
                    if len(parts[1]) != 3:
                        return None, info
                    v = Decimal(parts[0] + parts[1])
                else:
                    v = Decimal(parts[0] + "." + parts[1])
        else:
            v = Decimal(t)
    except InvalidOperation:
        return None, info
    return (-v if neg else v), info


def format_number(v, profile, minor=None, money=False):
    dec = profile["decimal"]
    thou = profile["thousands"]
    if minor is None:
        # plain number: keep natural scale, trim to at most 4 dp for display
        q = Decimal("0.0001")
        v = v.quantize(q, rounding=ROUND_HALF_UP).normalize()
        s = format(v, "f")
    else:
        q = Decimal(1).scaleb(-minor)
        v = v.quantize(q, rounding=ROUND_HALF_UP)
        s = format(v, "f")
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    if "." in s:
        ip, fp = s.split(".")
    else:
        ip, fp = s, ""
    groups = []
    while len(ip) > 3:
        groups.append(ip[-3:])
        ip = ip[:-3]
    groups.append(ip)
    out = thou.join(reversed(groups))
    if fp:
        out += dec + fp
    elif money and minor and minor > 0:
        out += dec + "0" * minor
    return ("-" if neg else "") + out


# --------------------------------------------------------------------------
# Column typing
# --------------------------------------------------------------------------
_CODE_HINTS = ("code", "id", "sku", "jan", "asin", "コード", "番号", "品番", "型番")
_DATE_HINTS = ("date", "日付", "日", "年月日")
_AMOUNT_HINTS = ("amount", "price", "total", "sum", "金額", "価格", "合計", "単価", "料金")


def _header_hint(header, hints):
    h = (header or "").lower()
    return any(x in h for x in hints)


def classify_column(header, values, sender):
    """Return 'date' | 'amount' | 'code' | 'text'."""
    vals = [v for v in values if str(v).strip()]
    if not vals:
        return "text"
    sample = vals[:60]
    wareki_hits = sum(1 for v in sample if is_wareki(normalize_fullwidth(str(v))))
    date_hits = 0
    num_hits = 0
    lead_zero = False
    for v in sample:
        sv = normalize_fullwidth(str(v).strip())
        if re.fullmatch(r"0\d+", sv.replace(",", "").replace(" ", "")):
            lead_zero = True
        if parse_date_with_order(sv, sender["date_order"]) or is_wareki(sv):
            date_hits += 1
        n, _ = parse_number(sv, sender["decimal"], sender["thousands"])
        if n is not None:
            num_hits += 1
    n = len(sample)
    if wareki_hits >= max(1, n // 3):
        return "date"
    if _header_hint(header, _CODE_HINTS) and num_hits >= n * 0.5:
        return "code"
    if lead_zero and num_hits >= n * 0.6 and not _header_hint(header, _AMOUNT_HINTS):
        return "code"
    if date_hits >= n * 0.6:
        return "date"
    if num_hits >= n * 0.6:
        return "amount" if (wareki_hits == 0) else "text"
    return "text"


# --------------------------------------------------------------------------
# FX: rate sources, cache, math
# --------------------------------------------------------------------------
FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest?base=USD"
ERAPI_URL = "https://open.er-api.com/v6/latest/USD"
MUFG_URL = "https://www.bk.mufg.jp/gdocs/rate/kinri_data_utf8.js"

LBL_FRANK = "ECB基準レートによる試算（レート日付：{date}）"
LBL_ERAPI = "参考レート（集計値）による試算 — 公式基準レートではありません"
LBL_ERAPI_ATTR = "出典：ExchangeRate-API (open.er-api.com)"
LBL_MUFG = "三菱UFJ銀行の適用レート（TTS/TTB・{dt}）で計算 — 送金手数料・受取側手数料は含みません"
LBL_MANUAL = "「{bank}」の適用レート（手入力{date}）で計算 — 送金手数料・受取側手数料は含みません"

# MUFG widget G-codes -> ISO currency (cross-checked against market rates
# published the same day; unknown codes are ignored by the parser).
MUFG_G2CCY = {
    "G001": "USD", "G020": "EUR", "G002": "GBP", "G005": "CHF",
    "G061": "AUD", "G074": "NZD", "G080": "ZAR", "G095": "TRY",
    "G069": "CNY",
}


def _http_get(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "FormatPassport/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_frankfurter(timeout=10):
    data = json.loads(_http_get(FRANKFURTER_URL, timeout).decode("utf-8"))
    rates = {k: Decimal(str(v)) for k, v in data["rates"].items()}
    rates["USD"] = Decimal(1)
    return {"source": "frankfurter", "base": "USD", "date": data.get("date", ""),
            "rates": rates, "fetched_at": datetime.now().isoformat(timespec="seconds")}


def fetch_erapi(timeout=10):
    data = json.loads(_http_get(ERAPI_URL, timeout).decode("utf-8"))
    if data.get("result") != "success":
        raise ValueError("er-api result != success")
    rates = {k: Decimal(str(v)) for k, v in data["rates"].items()}
    return {"source": "erapi", "base": "USD",
            "date": str(data.get("time_last_update_utc", ""))[:16],
            "rates": rates, "fetched_at": datetime.now().isoformat(timespec="seconds")}


_MUFG_PAIR = re.compile(r'"(G\d{3})(TTS|TTB)Z"\s*:\s*"([\d.]+)"')
_MUFG_DATE = re.compile(r'"G001DATE"\s*:\s*"([^"]+)"')


def parse_mufg_js(text):
    """Tolerant parser for MUFG's published kinri_data JS. Returns dict or None."""
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig", errors="replace")
    pairs = {}
    for code, kind, val in _MUFG_PAIR.findall(text):
        ccy = MUFG_G2CCY.get(code)
        if not ccy:
            continue
        try:
            pairs.setdefault(ccy, {})[kind] = Decimal(val)
        except InvalidOperation:
            continue
    out = {}
    for ccy, d in pairs.items():
        if "TTS" in d and "TTB" in d:
            out[ccy] = (d["TTS"], d["TTB"])
    if not out:
        return None
    m = _MUFG_DATE.search(text)
    return {"source": "mufg", "date": m.group(1) if m else "",
            "pairs": out, "fetched_at": datetime.now().isoformat(timespec="seconds")}


def fetch_mufg(timeout=10):
    parsed = parse_mufg_js(_http_get(MUFG_URL, timeout))
    if parsed is None:
        raise ValueError("MUFG rate file could not be parsed")
    return parsed


# --------------------------------------------------------------------------
# Official central-bank rate layer (Tier 1) + tiered merge
#
# Every rate carries provenance: which source published it and that
# source's tier. Tier 1 = a central bank / official publisher itself,
# Tier 2 = Frankfurter (ECB reference data redistributed), Tier 3 =
# open.er-api.com (aggregated, last resort only). A lower tier NEVER
# overrides a higher tier for the same currency.
# --------------------------------------------------------------------------
SOURCE_INFO = {
    "fred": ("FRED（米連邦準備制度 H.10）", 1),
    "rba": ("オーストラリア準備銀行（RBA）", 1),
    "nbp": ("ポーランド国立銀行（NBP）", 1),
    "cnb": ("チェコ国立銀行（CNB）", 1),
    "nbu": ("ウクライナ国立銀行（NBU）", 1),
    "bcb": ("ブラジル中央銀行（BCB / PTAX）", 1),
    "hkma": ("香港金融管理局（HKMA）", 1),
    "norges": ("ノルウェー中央銀行（Norges Bank）", 1),
    "frankfurter": ("ECB（Frankfurter経由）", 2),
    "erapi": ("ExchangeRate-API（集計値）", 3),
}
LBL_OFFICIAL = "公式レート（中央銀行）による試算（出典：{names}／レート日付：{dates}）"


def _bundle(source, rates, date, dates=None):
    name, tier = SOURCE_INFO[source]
    return {"source": source, "base": "USD", "date": date,
            "rates": dict(rates),
            "prov": {c: (source, tier) for c in rates},
            "dates": dates or {c: date for c in rates},
            "fetched_at": datetime.now().isoformat(timespec="seconds")}


# --- FRED (Federal Reserve H.10, fredgraph CSV, no key) ---
FRED_SERIES = {  # series -> (currency, 'usd_per' = USD per 1 ccy | 'per_usd')
    "DEXUSEU": ("EUR", "usd_per"), "DEXUSUK": ("GBP", "usd_per"),
    "DEXUSAL": ("AUD", "usd_per"), "DEXUSNZ": ("NZD", "usd_per"),
    "DEXJPUS": ("JPY", "per_usd"), "DEXCAUS": ("CAD", "per_usd"),
    "DEXCHUS": ("CNY", "per_usd"), "DEXSZUS": ("CHF", "per_usd"),
    "DEXKOUS": ("KRW", "per_usd"), "DEXHKUS": ("HKD", "per_usd"),
    "DEXINUS": ("INR", "per_usd"), "DEXMXUS": ("MXN", "per_usd"),
    "DEXBZUS": ("BRL", "per_usd"), "DEXTAUS": ("TWD", "per_usd"),
    "DEXSIUS": ("SGD", "per_usd"), "DEXMAUS": ("MYR", "per_usd"),
    "DEXTHUS": ("THB", "per_usd"), "DEXSFUS": ("ZAR", "per_usd"),
    "DEXNOUS": ("NOK", "per_usd"), "DEXSDUS": ("SEK", "per_usd"),
    "DEXDNUS": ("DKK", "per_usd"),
}
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + ",".join(FRED_SERIES)


def parse_fred_csv(text):
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    header = lines[0].split(",")
    last = None
    for ln in lines[1:]:
        cells = ln.split(",")
        if any(c not in ("", ".") for c in cells[1:]):
            last = cells
    if last is None:
        return None
    rates = {"USD": Decimal(1)}
    for i, sid in enumerate(header[1:], start=1):
        if sid not in FRED_SERIES or i >= len(last):
            continue
        raw = last[i]
        if raw in ("", "."):
            continue
        ccy, mode = FRED_SERIES[sid]
        v = Decimal(raw)
        rates[ccy] = (Decimal(1) / v) if mode == "usd_per" else v
    if len(rates) < 3:
        return None
    return _bundle("fred", rates, last[0])


def fetch_fred(timeout=10):
    timeout = max(timeout, 20)
    ids = list(FRED_SERIES)
    merged = None
    for i in range(0, len(ids), 11):
        url = ("https://fred.stlouisfed.org/graph/fredgraph.csv?id="
               + ",".join(ids[i:i + 11]))
        try:
            b = parse_fred_csv(_http_get(url, timeout).decode("utf-8", "replace"))
        except Exception:
            b = None  # no retries: respect the source's rate limits
        if b is None:
            continue
        if merged is None:
            merged = b
        else:
            for ccy, v in b["rates"].items():
                merged["rates"].setdefault(ccy, v)
                merged["prov"].setdefault(ccy, b["prov"][ccy])
                merged["dates"].setdefault(ccy, b["dates"].get(ccy, b["date"]))
            merged["date"] = max(merged["date"], b["date"])
    if merged is None or len(merged["rates"]) < 3:
        raise ValueError("FRED parse failed")
    return merged


# --- RBA (Reserve Bank of Australia RSS; values = foreign units per 1 AUD) ---
_RBA_ITEM = re.compile(r'<item rdf:about="[^"]*#([A-Z]{3})">(.*?)</item>', re.S)
_RBA_VAL = re.compile(r"<cb:value>([\d.]+)</cb:value>")
_RBA_DATE = re.compile(r"<dc:date>([^<]+)</dc:date>")


def parse_rba_xml(text):
    per_aud = {}
    dates = []
    for ccy, body in _RBA_ITEM.findall(text):
        m = _RBA_VAL.search(body)
        if m:
            per_aud[ccy] = Decimal(m.group(1))
        d = _RBA_DATE.search(body)
        if d:
            dates.append(d.group(1)[:10])
    if "USD" not in per_aud or len(per_aud) < 5:
        return None
    usd_per_aud = per_aud["USD"]
    rates = {c: (v / usd_per_aud) for c, v in per_aud.items()}
    rates["AUD"] = Decimal(1) / usd_per_aud
    rates["USD"] = Decimal(1)
    return _bundle("rba", rates, dates[0] if dates else "")


def fetch_rba(timeout=10):
    b = parse_rba_xml(_http_get(
        "https://www.rba.gov.au/rss/rss-cb-exchange-rates.xml", timeout).decode("utf-8", "replace"))
    if b is None:
        raise ValueError("RBA parse failed")
    return b


# --- NBP (National Bank of Poland, table A JSON; mid = PLN per 1 unit) ---
def parse_nbp_json(text):
    data = json.loads(text)[0]
    per_pln = {}
    for r in data["rates"]:
        per_pln[r["code"]] = Decimal(str(r["mid"]))
    if "USD" not in per_pln:
        return None
    # per_pln[ccy] is PLN per 1 ccy; USD-based rate = (PLN per USD)/(PLN per ccy)
    pln_per_usd = per_pln["USD"]
    rates = {c: (pln_per_usd / v) for c, v in per_pln.items()}
    rates["PLN"] = pln_per_usd
    rates["USD"] = Decimal(1)
    return _bundle("nbp", rates, data.get("effectiveDate", ""))


def fetch_nbp(timeout=10):
    b = parse_nbp_json(_http_get(
        "https://api.nbp.pl/api/exchangerates/tables/A/?format=json", timeout).decode("utf-8"))
    if b is None:
        raise ValueError("NBP parse failed")
    return b


# --- CNB (Czech National Bank daily txt; Rate = CZK per Amount units) ---
def parse_cnb_txt(text):
    per_czk = {}
    day = ""
    for ln in text.splitlines():
        if " #" in ln and "|" not in ln:
            day = ln.split(" #")[0].strip()
        parts = ln.split("|")
        if len(parts) == 5 and re.fullmatch(r"[A-Z]{3}", parts[3].strip()):
            amount = Decimal(parts[2].strip())
            rate = Decimal(parts[4].strip())
            per_czk[parts[3].strip()] = rate / amount
    if "USD" not in per_czk:
        return None
    czk_per_usd = per_czk["USD"]
    rates = {c: (czk_per_usd / v) for c, v in per_czk.items()}
    rates["CZK"] = czk_per_usd
    rates["USD"] = Decimal(1)
    return _bundle("cnb", rates, day)


def fetch_cnb(timeout=10):
    b = parse_cnb_txt(_http_get(
        "https://www.cnb.cz/en/financial-markets/foreign-exchange-market/"
        "central-bank-exchange-rate-fixing/central-bank-exchange-rate-fixing/daily.txt",
        timeout).decode("utf-8", "replace"))
    if b is None:
        raise ValueError("CNB parse failed")
    return b


# --- NBU (National Bank of Ukraine JSON; rate = UAH per 1 unit) ---
def parse_nbu_json(text):
    data = json.loads(text)
    per_uah = {}
    day = ""
    for r in data:
        try:
            per_uah[r["cc"]] = Decimal(str(r["rate"]))
            day = r.get("exchangedate", day)
        except Exception:
            continue
    if "USD" not in per_uah:
        return None
    uah_per_usd = per_uah["USD"]
    rates = {c: (uah_per_usd / v) for c, v in per_uah.items()}
    rates["UAH"] = uah_per_usd
    rates["USD"] = Decimal(1)
    return _bundle("nbu", rates, day)


def fetch_nbu(timeout=10):
    b = parse_nbu_json(_http_get(
        "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json",
        timeout).decode("utf-8"))
    if b is None:
        raise ValueError("NBU parse failed")
    return b


# --- BCB PTAX (Banco Central do Brasil OData; cotacaoVenda = BRL per unit) ---
BCB_BASE = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata"


def _bcb_quote(ccy, day, timeout):
    url = (BCB_BASE + "/CotacaoMoedaDia(moeda=@moeda,dataCotacao=@dataCotacao)"
           "?@moeda='%s'&@dataCotacao='%s'&$format=json" % (ccy, day))
    data = json.loads(_http_get(url, timeout).decode("utf-8"))
    vals = data.get("value") or []
    if not vals:
        return None
    # cotacaoVenda is BRL per 1 unit of the currency; prefer the closing
    # bulletin (Fechamento PTAX) when the day has one.
    closing = [v for v in vals if str(v.get("tipoBoletim", "")).startswith("Fechamento")]
    chosen = closing[-1] if closing else vals[-1]
    return Decimal(str(chosen["cotacaoVenda"]))


def fetch_bcb(timeout=8):
    from datetime import timedelta
    moedas = json.loads(_http_get(BCB_BASE + "/Moedas?$format=json", timeout).decode("utf-8"))
    ccys = [m["simbolo"] for m in moedas.get("value", [])
            if m["simbolo"] in MINOR_UNITS]
    today = date.today()
    base_day = None
    per_brl = {}
    for back in range(0, 8):
        d = (today - timedelta(days=back)).strftime("%m-%d-%Y")
        v = _bcb_quote("USD", d, timeout)
        if v is not None:
            base_day, per_brl["USD"] = d, v
            break
    if base_day is None:
        raise ValueError("BCB: no bulletin in last 7 days")
    from concurrent.futures import ThreadPoolExecutor
    others = [c for c in ccys if c != "USD"]
    with ThreadPoolExecutor(max_workers=5) as pool:
        futs = {pool.submit(_bcb_quote, c, base_day, timeout): c for c in others}
        for fut, ccy in futs.items():
            try:
                v = fut.result()
            except Exception:
                v = None
            if v is not None:
                per_brl[ccy] = v
    brl_per_usd = per_brl["USD"]
    rates = {c: (brl_per_usd / v) for c, v in per_brl.items()}
    rates["BRL"] = brl_per_usd
    rates["USD"] = Decimal(1)
    m, d, y = base_day.split("-")
    return _bundle("bcb", rates, "%s-%s-%s" % (y, m, d))


# --- HKMA (Hong Kong Monetary Authority; record fields = HKD per 1 unit) ---
def parse_hkma_json(text):
    data = json.loads(text)
    recs = data["result"]["records"]
    if not recs:
        return None
    rec = max(recs, key=lambda r: r.get("end_of_day", ""))
    per_hkd = {}
    for k, v in rec.items():
        code = k.upper()
        if len(code) == 3 and code in MINOR_UNITS and isinstance(v, (int, float)) and v:
            per_hkd[code] = Decimal(str(v))
    if "USD" not in per_hkd:
        return None
    hkd_per_usd = per_hkd["USD"]
    rates = {c: (hkd_per_usd / v) for c, v in per_hkd.items()}
    rates["HKD"] = hkd_per_usd
    rates["USD"] = Decimal(1)
    return _bundle("hkma", rates, rec.get("end_of_day", ""))


def fetch_hkma(timeout=10):
    from datetime import timedelta
    frm = (date.today() - timedelta(days=30)).isoformat()
    to = date.today().isoformat()
    url = ("https://api.hkma.gov.hk/public/market-data-and-statistics/"
           "monthly-statistical-bulletin/er-ir/er-eeri-daily?from=%s&to=%s" % (frm, to))
    b = parse_hkma_json(_http_get(url, timeout).decode("utf-8"))
    if b is None:
        raise ValueError("HKMA parse failed")
    return b


# --- Norges Bank (SDMX JSON; values = NOK per 1 unit of base currency) ---
def parse_norges_json(text):
    data = json.loads(text)
    struct = data["data"]["structure"]["dimensions"]["series"]
    dim_ids = [d["id"] for d in struct]
    base_idx = dim_ids.index("BASE_CUR")
    currencies = [v["id"] for v in struct[base_idx]["values"]]
    series = data["data"]["dataSets"][0]["series"]
    obs_dims = data["data"]["structure"]["dimensions"]["observation"]
    periods = [v["id"] for dim in obs_dims if dim["id"] == "TIME_PERIOD"
               for v in dim["values"]]
    # UNIT_MULT series attribute: '2' means the value is quoted per 100 units
    attr_defs = data["data"]["structure"].get("attributes", {}).get("series", [])
    mult_pos, mult_vals = None, []
    for i, a in enumerate(attr_defs):
        if a.get("id") == "UNIT_MULT":
            mult_pos, mult_vals = i, [v["id"] for v in a["values"]]
    per_nok = {}
    usd_period = ""
    for key, s in series.items():
        idx = int(key.split(":")[base_idx])
        ccy = currencies[idx]
        obs = s.get("observations", {})
        if not obs:
            continue
        last_key = sorted(obs, key=lambda x: int(x))[-1]
        value = Decimal(str(obs[last_key][0]))
        if mult_pos is not None:
            attrs = s.get("attributes") or []
            if mult_pos < len(attrs) and attrs[mult_pos] is not None:
                mult = int(mult_vals[attrs[mult_pos]])
                if mult:
                    value = value / (Decimal(10) ** mult)
        per_nok[ccy] = value
        if ccy == "USD" and periods:
            usd_period = periods[int(last_key)] if int(last_key) < len(periods) else ""
    if "USD" not in per_nok:
        return None
    nok_per_usd = per_nok["USD"]
    rates = {c: (nok_per_usd / v) for c, v in per_nok.items()
             if c in MINOR_UNITS or c == "NOK"}
    rates["NOK"] = nok_per_usd
    rates["USD"] = Decimal(1)
    return _bundle("norges", rates, usd_period)


def fetch_norges(timeout=12):
    url = ("https://data.norges-bank.no/api/data/EXR/B..NOK.SP"
           "?format=sdmx-json&lastNObservations=1")
    b = parse_norges_json(_http_get(url, timeout).decode("utf-8"))
    if b is None:
        raise ValueError("Norges parse failed")
    return b


OFFICIAL_FETCHERS = [
    ("fred", fetch_fred), ("rba", fetch_rba), ("nbp", fetch_nbp),
    ("cnb", fetch_cnb), ("nbu", fetch_nbu), ("norges", fetch_norges),
    ("hkma", fetch_hkma), ("bcb", fetch_bcb),
]


def fetch_official_layer(timeout=8):
    """Try every official source (concurrently); returns (bundles, errors)
    with bundles kept in OFFICIAL_FETCHERS priority order."""
    from concurrent.futures import ThreadPoolExecutor
    results, errors = {}, {}
    with ThreadPoolExecutor(max_workers=len(OFFICIAL_FETCHERS)) as pool:
        futs = {pool.submit(fn, timeout): name for name, fn in OFFICIAL_FETCHERS}
        for fut, name in futs.items():
            try:
                results[name] = fut.result()
            except Exception as exc:  # a dead source must never break the app
                errors[name] = str(exc)[:120]
    bundles = [results[name] for name, _ in OFFICIAL_FETCHERS if name in results]
    return bundles, errors


def merge_rate_bundles(bundles):
    """Merge bundles in priority order: first writer wins per currency."""
    rates, prov, dates = {}, {}, {}
    for b in bundles:
        for ccy, v in b.get("rates", {}).items():
            if ccy not in rates:
                rates[ccy] = v
                prov[ccy] = tuple(b.get("prov", {}).get(ccy, (b.get("source", "?"), 3)))
                dates[ccy] = b.get("dates", {}).get(ccy, b.get("date", ""))
    return {"source": "merged", "base": "USD", "date": "",
            "rates": rates, "prov": prov, "dates": dates,
            "fetched_at": datetime.now().isoformat(timespec="seconds")}


def tier_coverage(bundle):
    cov = {1: 0, 2: 0, 3: 0}
    for ccy, (_src, tier) in bundle.get("prov", {}).items():
        if tier in cov:
            cov[tier] += 1
    return cov


def fetch_all_rates(timeout=8):
    """Official layer first, then Frankfurter (ECB), then er-api fill."""
    bundles, errors = fetch_official_layer(timeout=timeout)
    try:
        fb = fetch_frankfurter(timeout=timeout)
        fb["prov"] = {c: ("frankfurter", 2) for c in fb["rates"]}
        fb["dates"] = {c: fb.get("date", "") for c in fb["rates"]}
        bundles.append(fb)
    except Exception as exc:
        errors["frankfurter"] = str(exc)[:120]
    try:
        eb = fetch_erapi(timeout=timeout)
        eb["prov"] = {c: ("erapi", 3) for c in eb["rates"]}
        eb["dates"] = {c: eb.get("date", "") for c in eb["rates"]}
        bundles.append(eb)
    except Exception as exc:
        errors["erapi"] = str(exc)[:120]
    return merge_rate_bundles(bundles), errors


def app_data_dir():
    if sys.platform == "darwin":
        # macOS standard per-user application data location.
        d = os.path.join(os.path.expanduser("~"),
                         "Library", "Application Support", "FormatPassport")
    else:
        base = os.environ.get("APPDATA")
        if base:
            d = os.path.join(base, "FormatPassport")
        else:
            d = os.path.join(os.path.expanduser("~"), ".formatpassport")
    os.makedirs(d, exist_ok=True)
    return d


def _json_default(o):
    if isinstance(o, Decimal):
        return str(o)
    raise TypeError


def save_fx_cache(cache, directory=None):
    directory = directory or app_data_dir()
    path = os.path.join(directory, "fx_cache.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, default=_json_default)
    return path


def load_fx_cache(directory=None):
    directory = directory or app_data_dir()
    path = os.path.join(directory, "fx_cache.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            cache = json.load(fh)
        for key, bundle in list(cache.items()):
            if isinstance(bundle, dict) and "rates" in bundle:
                bundle["rates"] = {k: Decimal(v) for k, v in bundle["rates"].items()}
                if "prov" in bundle:
                    bundle["prov"] = {k: (v[0], int(v[1])) for k, v in bundle["prov"].items()}
        if "mufg" in cache:
            cache["mufg"]["pairs"] = {
                k: (Decimal(v[0]), Decimal(v[1])) for k, v in cache["mufg"]["pairs"].items()}
        return cache
    except Exception:
        return {}


def cross_rate(rates, from_ccy, to_ccy):
    """Units of to_ccy per 1 unit of from_ccy, from a USD-based table."""
    if from_ccy == to_ccy:
        return Decimal(1)
    rf = rates.get(from_ccy)
    rt = rates.get(to_ccy)
    if rf is None or rt is None or rf == 0:
        return None
    return rt / rf


def fx_convert(amount, from_ccy, to_ccy, mode, ctx):
    """Convert Decimal amount. Returns (converted, rate_used_str, label) or
    (None, reason, label) when impossible in the chosen mode.

    ctx keys by mode:
      ref:    {'bundle': rate bundle dict}
      bank:   {'mufg': parsed mufg dict}
      manual: {'bank_name','date_memo','tts','ttb','rate'} (Decimals/str)
    """
    to_minor = minor_unit(to_ccy)
    q = Decimal(1).scaleb(-to_minor)
    if from_ccy == to_ccy:
        return amount.quantize(q, rounding=ROUND_HALF_UP), "1", ""
    if mode == "ref":
        bundle = ctx.get("bundle") or {}
        rate = cross_rate(bundle.get("rates", {}), from_ccy, to_ccy)
        if rate is None:
            return None, "no rate for %s->%s" % (from_ccy, to_ccy), ""
        out = (amount * rate).quantize(q, rounding=ROUND_HALF_UP)
        prov = bundle.get("prov") or {}
        if prov:
            tiers, names, dates = [], [], []
            for ccy in (from_ccy, to_ccy):
                if ccy == "USD":
                    continue
                src, tier = prov.get(ccy, ("erapi", 3))
                tiers.append(tier)
                nm = SOURCE_INFO.get(src, (src, tier))[0]
                if nm not in names:
                    names.append(nm)
                dt = bundle.get("dates", {}).get(ccy, "")
                if dt and dt not in dates:
                    dates.append(dt)
            worst = max(tiers) if tiers else 3
            if worst <= 2:
                label = LBL_OFFICIAL.format(names="・".join(names),
                                            dates="／".join(dates))
            else:
                label = LBL_ERAPI + "／" + LBL_ERAPI_ATTR
        elif bundle.get("source") == "frankfurter":
            label = LBL_FRANK.format(date=bundle.get("date", ""))
        else:
            label = LBL_ERAPI + "／" + LBL_ERAPI_ATTR
        return out, str(rate.normalize()), label
    if mode in ("bank", "manual"):
        if mode == "bank":
            mufg = ctx.get("mufg") or {}
            pairs = mufg.get("pairs", {})
            label = LBL_MUFG.format(dt=mufg.get("date", ""))
            src_name = "MUFG"
        else:
            pairs = {}
            tts, ttb = ctx.get("tts"), ctx.get("ttb")
            if tts and ttb:
                other = to_ccy if from_ccy == "JPY" else from_ccy
                pairs = {other: (Decimal(str(tts)), Decimal(str(ttb)))}
            label = LBL_MANUAL.format(bank=ctx.get("bank_name", ""),
                                       date=("・" + ctx["date_memo"]) if ctx.get("date_memo") else "")
            src_name = ctx.get("bank_name", "")
        single = ctx.get("rate") if mode == "manual" else None
        if single:
            rate = Decimal(str(single))
            out = (amount * rate).quantize(q, rounding=ROUND_HALF_UP)
            return out, str(rate.normalize()), label
        if from_ccy == "JPY" and to_ccy in pairs:
            tts, _ = pairs[to_ccy]
            out = (amount / tts).quantize(q, rounding=ROUND_HALF_UP)
            return out, "1 %s = %s JPY (TTS)" % (to_ccy, tts), label
        if to_ccy == "JPY" and from_ccy in pairs:
            _, ttb = pairs[from_ccy]
            out = (amount * ttb).quantize(q, rounding=ROUND_HALF_UP)
            return out, "1 %s = %s JPY (TTB)" % (from_ccy, ttb), label
        return None, "bank rate not available for %s->%s (%s)" % (from_ccy, to_ccy, src_name), label
    return None, "unknown mode", ""


# --------------------------------------------------------------------------
# Conversion engine
# --------------------------------------------------------------------------
class ReviewItem:
    def __init__(self, row, col, header, original, kind, candidates, pattern_key, reason=""):
        self.row, self.col, self.header = row, col, header
        self.original, self.kind = original, kind
        self.candidates = candidates      # [{key,label,output}]
        self.pattern_key = pattern_key
        self.reason = reason

    def to_dict(self):
        return {"row": self.row, "col": self.col, "header": self.header,
                "original": self.original, "kind": self.kind,
                "candidates": self.candidates, "pattern_key": self.pattern_key,
                "reason": self.reason}


class ConvertResult:
    def __init__(self):
        self.rows = []
        self.changes = []   # dicts: row,col,before,after,kind,reason
        self.reviews = []   # ReviewItem
        self.report = {}


def _shape(s):
    return re.sub(r"\d", "9", s)


def convert_table(table, sender_code, receiver_code, opts=None, resolutions=None, fx=None):
    """opts: {'fix_fullwidth_text': bool}
    resolutions: {pattern_key or 'r{row}c{col}': output_text}
    fx: None or {'mode':..., 'ctx': {...}} (enabled only when not None)
    """
    opts = opts or {}
    resolutions = resolutions or {}
    sender = BY_CODE[sender_code]
    receiver = BY_CODE[receiver_code]
    result = ConvertResult()
    out_rows = [list(r) for r in table.rows]
    counts = {"date": 0, "wareki": 0, "number": 0, "fx": 0, "fullwidth": 0,
              "preserved_code": 0, "unresolved": 0}
    fx_label_used = ""
    fx_rate_used = ""

    # Pass 1: date order proof per column
    col_types = []
    date_orders = {}
    for ci, header in enumerate(table.headers):
        values = [r[ci] for r in table.rows]
        ctype = classify_column(header, values, sender)
        col_types.append(ctype)
        if ctype == "date":
            order, _why = analyze_date_column(
                [normalize_fullwidth(str(v).strip()) for v in values], sender["date_order"])
            date_orders[ci] = order

    # Pass 1b: separator-role proof per amount column, from values whose
    # shape is unambiguous (multi-group thousands, or a decimal tail that
    # is not exactly 3 digits).
    def _setproof(proof, sep, role):
        if sep in proof and proof[sep] != role:
            proof[sep] = "conflict"
        else:
            proof[sep] = role

    num_proofs = {}
    for ci, header in enumerate(table.headers):
        if col_types[ci] != "amount":
            continue
        proof = {}
        for row in table.rows:
            v = normalize_fullwidth(str(row[ci]).strip())
            v, _c = _strip_currency(v)
            for ch in _SPACE_CHARS + "'":
                v = v.replace(ch, "")
            m = re.fullmatch(r"\d{1,3}([.,])\d{3}(?:[.,]\d{3})+(?:[.,]\d{1,4})?", v)
            if m:
                _setproof(proof, m.group(1), "thousands")
            if "." in v and "," in v:
                last = "." if v.rfind(".") > v.rfind(",") else ","
                other = "," if last == "." else "."
                _setproof(proof, last, "decimal")
                _setproof(proof, other, "thousands")
            m = re.fullmatch(r"\d+([.,])(\d{1,2}|\d{4,})", v)
            if m:
                _setproof(proof, m.group(1), "decimal")
        num_proofs[ci] = proof

    for ci, header in enumerate(table.headers):
        ctype = col_types[ci]
        for ri, row in enumerate(table.rows):
            raw = row[ci]
            s = str(raw)
            st = s.strip()
            if not st:
                continue
            cell_key = "r%dc%d" % (ri, ci)
            nrm = normalize_fullwidth(st)

            if ctype == "code":
                _v, _i = parse_number(st, sender["decimal"], sender["thousands"])
                if _v is not None:
                    counts["preserved_code"] += 1  # kept verbatim on purpose
                continue

            if ctype == "date":
                # wareki handling
                if is_wareki(nrm):
                    d = wareki_to_date(nrm)
                    if d is None:
                        continue
                    if receiver_code == "JP":
                        out = date_to_wareki(d, "full")
                    else:
                        out = format_date(d, receiver)
                    if out != st:
                        out_rows[ri][ci] = out
                        result.changes.append({
                            "row": ri, "col": ci, "before": st, "after": out,
                            "kind": "wareki", "reason": "wareki->date"})
                        counts["wareki"] += 1
                    continue
                # Gregorian -> wareki when receiver is JP and sender is not
                d_norm = parse_date_with_order(nrm, sender["date_order"])
                _info = classify_numeric_date(nrm)
                had_year = not (_info and _info["year_pos"] == "none")
                order = date_orders.get(ci)
                if order is None:
                    # undecidable column: check cell-level ambiguity
                    d_dmy = parse_date_with_order(nrm, "DMY")
                    d_mdy = parse_date_with_order(nrm, "MDY")
                    if d_dmy and d_mdy and d_dmy != d_mdy:
                        pk = "date:c%d" % ci
                        cands = []
                        for lbl, dd in (("DMY", d_dmy), ("MDY", d_mdy)):
                            cands.append({"key": lbl, "label": "%s → %s" % (lbl, dd.isoformat()),
                                          "output": _date_output(dd, receiver, receiver_code, had_year)})
                        chosen = resolutions.get(pk) or resolutions.get(cell_key)
                        if chosen:
                            out_rows[ri][ci] = chosen
                            counts["date"] += 1
                        else:
                            result.reviews.append(ReviewItem(
                                ri, ci, header, st, "date", cands, pk,
                                "ambiguous date (both readings valid)"))
                            counts["unresolved"] += 1
                        continue
                    d_norm = d_dmy or d_mdy
                else:
                    d_norm = parse_date_with_order(nrm, order)
                if d_norm is None:
                    continue
                out = _date_output(d_norm, receiver, receiver_code, had_year)
                if out != st:
                    out_rows[ri][ci] = out
                    reason = "date order"
                    result.changes.append({
                        "row": ri, "col": ci, "before": st, "after": out,
                        "kind": "date", "reason": reason})
                    counts["date"] += 1
                continue

            if ctype == "amount":
                # leading-zero values are codes, never numbers
                squashed = nrm.replace(",", "").replace(" ", "").replace(".", "")
                if re.fullmatch(r"0\d+", squashed) and "." not in nrm and "," not in nrm.replace(sender["thousands"], ""):
                    counts["preserved_code"] += 1
                    continue
                v, info = parse_number(st, sender["decimal"], sender["thousands"],
                                       proof=num_proofs.get(ci))
                if v is None:
                    continue
                pk = "num:c%d:%s" % (ci, _shape(st))
                if info.get("ambiguous"):
                    alt = info.get("alt")
                    cands = [
                        {"key": "main", "label": "%s (%s)" % (
                            format_number(v, receiver), _num_meaning(v, sender)),
                         "output": None},
                        {"key": "alt", "label": "%s (%s)" % (
                            format_number(alt, receiver), _num_meaning(alt, sender)),
                         "output": None},
                    ]
                    chosen = resolutions.get(pk) or resolutions.get(cell_key)
                    chosen_key = resolutions.get(pk + ":key") or resolutions.get(cell_key + ":key")
                    if chosen is not None:
                        out_rows[ri][ci] = chosen
                        counts["number"] += 1
                    else:
                        for c, vv in zip(cands, (v, alt)):
                            c["output"] = _amount_output(vv, sender, receiver, fx, header)[0]
                        result.reviews.append(ReviewItem(
                            ri, ci, header, st, "number", cands, pk,
                            "ambiguous number (decimal or thousands separator)"))
                        counts["unresolved"] += 1
                    continue
                out, fxinfo = _amount_output(v, sender, receiver, fx, header)
                if fxinfo:
                    fx_rate_used, fx_label_used = fxinfo
                if out != st:
                    out_rows[ri][ci] = out
                    kind = "fx" if fx else "number"
                    result.changes.append({
                        "row": ri, "col": ci, "before": st, "after": out,
                        "kind": kind, "reason": "number format" if not fx else "fx convert"})
                    counts["fx" if fx else "number"] += 1
                elif nrm != st:
                    counts["fullwidth"] += 1
                continue

            # text columns: only optional fullwidth fix
            if opts.get("fix_fullwidth_text") and nrm != st:
                out_rows[ri][ci] = nrm
                result.changes.append({
                    "row": ri, "col": ci, "before": st, "after": nrm,
                    "kind": "fullwidth", "reason": "fullwidth->halfwidth"})
                counts["fullwidth"] += 1

    result.rows = out_rows
    result.report = {
        "counts": counts,
        "changes": len(result.changes),
        "unresolved": counts["unresolved"],
        "sender": sender_code, "receiver": receiver_code,
        "sender_currency": sender["currency"], "receiver_currency": receiver["currency"],
        "fx_label": fx_label_used, "fx_rate": fx_rate_used,
        "col_types": col_types,
    }
    return result


def _date_output(d, receiver, receiver_code, had_year=True):
    if not had_year:
        return format_date_short(d, receiver)
    return format_date(d, receiver)


def _num_meaning(v, sender):
    return "value %s" % format(v.normalize(), "f")


def _amount_output(v, sender, receiver, fx, header):
    """Returns (text, fxinfo_or_None). fxinfo = (rate_str, label)."""
    if fx:
        conv, rate_str, label = fx_convert(
            v, sender["currency"], receiver["currency"], fx["mode"], fx["ctx"])
        if conv is not None:
            minor = minor_unit(receiver["currency"])
            return format_number(conv, receiver, minor=minor, money=True), (rate_str, label)
    return format_number(v, receiver), None


def build_report_text(result, lang_t=None):
    r = result.report
    lines = []
    lines.append("FormatPassport conversion report")
    lines.append("sender: %s (%s) -> receiver: %s (%s)" % (
        r["sender"], r["sender_currency"], r["receiver"], r["receiver_currency"]))
    c = r["counts"]
    lines.append("dates converted: %d" % c["date"])
    lines.append("wareki converted: %d" % c["wareki"])
    lines.append("numbers reformatted: %d" % c["number"])
    lines.append("fx converted cells: %d" % c["fx"])
    lines.append("fullwidth fixed: %d" % c["fullwidth"])
    lines.append("code-like values preserved: %d" % c["preserved_code"])
    lines.append("unresolved (kept as original): %d" % r["unresolved"])
    if r.get("fx_rate"):
        lines.append("fx rate used: %s" % r["fx_rate"])
    if r.get("fx_label"):
        lines.append("fx basis: %s" % r["fx_label"])
    return "\n".join(lines)

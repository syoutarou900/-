# -*- coding: utf-8 -*-
"""MatchDetective core: table IO, normalization, key proposal, reconciliation.

Semi-auto rule: the engine proposes keys and candidate pairings; the human
makes the final pairing decisions. Source files are never modified.
"""
import csv
import io
import itertools
import json
import os
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# ---------------------------------------------------------------------------
# Table IO (same approach as FormatPassport)
# ---------------------------------------------------------------------------


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


def save_table_csv(table, path, delimiter=",", encoding="utf-8-sig"):
    data = table_to_csv_text(table, delimiter, encoding)
    with open(path, "wb") as fh:
        fh.write(data)


def save_table_xlsx(table, path):
    from openpyxl import Workbook  # lazy
    wb = Workbook()
    ws = wb.active
    ws.append(table.headers)
    for r in table.rows:
        ws.append(r)
    wb.save(path)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
_CURRENCY_CHARS = "¥$€£₹₽₩¢円"
_SMALL_KANA = str.maketrans("ァィゥェォッャュョヮヵヶ", "アイウエオツヤユヨワカケ")


def base_normalize(s):
    """NFKC (fullwidth->halfwidth, halfwidth kana->fullwidth, ㈱->(株) ...)
    plus case-folding."""
    if s is None:
        return ""
    return unicodedata.normalize("NFKC", str(s)).casefold()


def parse_number(s):
    """Parse a number tolerant of locale formats. Returns Decimal or None.

    1,000 / 1000 / １，０００ all become 1000; 1.234,56 and 1,234.56
    both become 1234.56. A lone separator followed by exactly 3 digits in
    a grouping pattern (1.234 / 1,234) is read as a thousands separator.
    """
    if s is None:
        return None
    t = base_normalize(str(s)).strip()
    if not t:
        return None
    for ch in _CURRENCY_CHARS:
        t = t.replace(ch, "")
    t = t.strip().replace(" ", "").replace("'", "")
    # trailing/leading currency codes
    t = re.sub(r"(?i)^(jpy|usd|eur|gbp|chf|cny|aud|krw)\s*", "", t)
    t = re.sub(r"(?i)\s*(jpy|usd|eur|gbp|chf|cny|aud|krw)$", "", t)
    if not t:
        return None
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg = True
        t = t[1:-1]
    if t.startswith("+"):
        t = t[1:]
    elif t.startswith("-"):
        neg = True
        t = t[1:]
    if not re.fullmatch(r"[0-9][0-9.,]*", t):
        return None
    has_dot, has_comma = "." in t, "," in t
    if has_dot and has_comma:
        if t.rfind(".") > t.rfind(","):
            t = t.replace(",", "")
        else:
            t = t.replace(".", "").replace(",", ".")
    elif has_comma:
        parts = t.split(",")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]) and len(parts[0]) <= 3:
            t = "".join(parts)                    # thousands grouping
        elif len(parts) == 2:
            t = parts[0] + "." + parts[1]         # decimal comma
        else:
            t = t.replace(",", "")
    elif has_dot:
        parts = t.split(".")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]) and len(parts[0]) <= 3 \
                and len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3 and parts[0] != "0"):
            t = "".join(parts)                    # thousands grouping (EU style)
    try:
        d = Decimal(t)
    except InvalidOperation:
        return None
    return -d if neg else d


def fmt_decimal(d):
    """Stable string for a Decimal (1000.00 -> '1000')."""
    if d is None:
        return ""
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


# --- legal-entity forms -----------------------------------------------------
_JP_FORMS = ["株式会社", "有限会社", "合同会社", "合名会社", "合資会社",
             "一般社団法人", "一般財団法人", "公益社団法人", "公益財団法人",
             "医療法人", "学校法人", "社会福祉法人", "特定非営利活動法人",
             "(株)", "(有)", "（株）", "（有）", "(同)", "（同）"]
_KR_FORMS = ["주식회사", "(주)", "유한회사", "유한책임회사", "합자회사", "합명회사",
             "(유)", "(합)"]
_CN_FORMS = ["股份有限公司", "有限责任公司", "有限公司"]
# Arabic generic/company forms (phrases, matched as substrings)
_AR_FORMS = ["شركة ذات مسؤولية محدودة", "ذات مسؤولية محدودة",
             "شركة مساهمة", "مؤسسة فردية", "ذ.م.م", "ذ م م",
             "ش.م.م", "ش م م", "شركة", "مؤسسة"]
# Turkish forms (phrases on the Turkish-folded text)
_TR_FORMS = ["limited şirketi", "ltd. şti.", "ltd. sti.", "koll. şti.",
             "kom. şti.", "a.ş.", "a.s.", "şti.", "sti."]
# Russian native forms (standalone words only, applied by regex)
_RU_FORMS = ["ооо", "оао", "пао", "ао", "зао", "ип"]
# Western forms are matched token-wise (after punctuation splitting).
_LEGAL_TOKENS = {
    # EN / US / Commonwealth
    "inc", "corp", "corporation", "ltd", "limited", "llc", "llp", "lp",
    "co", "company", "pc", "pty", "pte", "pvt", "bvba",
    # DE / AT / CH
    "gmbh", "ag", "kg", "kgaa", "ohg", "ek", "ug", "eg",
    # FR / ES / IT / PT
    "sa", "sas", "sarl", "sl", "srl", "spa", "sca", "lda",
    # NL / BE
    "bv", "nv", "vof", "cv",
    # Nordics
    "ab", "as", "oy", "oyj", "aps", "ehf",
    # PT (Brazil / Portugal)
    "ltda", "limitada", "eireli", "epp", "me", "lda", "unipessoal",
    # RU romanized
    "ooo", "pao", "ao", "zao", "ip",
    # ID (PT is a prefix form in Indonesia; token position does not matter)
    "pt", "perseroan", "terbatas", "cv", "ud", "firma", "fa", "koperasi",
    # others
    "sro", "spzoo", "kft", "zrt", "sarl",
}
_LEGAL_PHRASES = [r"s\.?a\.?\s*de\s*c\.?v\.?", r"s\.?a\.?\s*de\s*c\.?v",
                  r"sdn\.?\s*bhd\.?", r"p\.?t\.?", r"c\.?v\.?",
                  r"s\.a\.s\.?", r"s\.a\.r\.l\.?", r"s\.a\.?", r"s\.l\.?",
                  r"s\.r\.l\.?", r"l\.l\.c\.?", r"l\.l\.p\.?", r"p\.l\.c\.?",
                  r"p\.c\.?", r"e\.k\.?", r"s\.c\.a\.?"]


def normalize_company(s):
    """Company-name comparison key: legal forms stripped, case/width/
    punctuation/spacing absorbed, kana small forms unified."""
    t = base_normalize(s)
    # Turkish fold: dotted/dotless i variants merge (İ casefolds to i+combining dot)
    t = t.replace("i̇", "i").replace("ı", "i")
    for phrase in _LEGAL_PHRASES:
        t = re.sub(phrase, " ", t)
    for form in _JP_FORMS + _KR_FORMS + _CN_FORMS + _AR_FORMS + _TR_FORMS:
        t = t.replace(form.casefold(), " ")
    for form in _RU_FORMS:
        t = re.sub(r"(?<![0-9a-zа-яё])" + form + r"(?![0-9a-zа-яё])", " ", t)
    tokens = re.findall(r"[0-9a-z]+|[^\s0-9a-z]", t)
    kept = []
    buf = ""
    for tok in tokens:
        if re.fullmatch(r"[0-9a-z]+", tok):
            if tok in _LEGAL_TOKENS:
                if buf:
                    kept.append(buf)
                    buf = ""
                continue
            buf += tok
        else:
            if buf:
                kept.append(buf)
                buf = ""
            kept.append(tok)
    if buf:
        kept.append(buf)
    # re-join: drop pure-punctuation tokens and legal tokens glued in CJK runs
    out = []
    for tok in kept:
        if re.fullmatch(r"[0-9a-z]+", tok):
            out.append(tok)
        elif tok.strip("()[]{}.,&・/\\-_'\"«»„“”‚‘’"):
            out.append(tok)
    t = "".join(out)
    t = t.translate(_SMALL_KANA)
    if t.endswith("集团"):            # CN group suffix (trailing position only)
        t = t[:-2]
    return t.strip()


# ---------------------------------------------------------------------------
# Kana folding (for corporate-number registry furigana identity checks)
# ---------------------------------------------------------------------------
def kana_fold(s):
    """Deterministic kana comparison key: NFKC (halfwidth kana ->
    fullwidth), hiragana -> katakana, small kana unified, the long-vowel
    mark and all spaces/punctuation dropped."""
    t = unicodedata.normalize("NFKC", "" if s is None else str(s))
    t = t.translate({c: chr(c + 0x60) for c in range(0x3041, 0x3097)})
    t = t.translate(_SMALL_KANA)
    t = t.translate(str.maketrans({"ヰ": "イ", "ヱ": "エ", "ヲ": "オ"}))
    t = re.sub(r"[\s・･\-‐ー―.,、。:：;；()\[\]（）「」『』'\"]+", "", t)
    return t


def strip_jp_legal(s):
    """Remove Japanese legal-form substrings ( 株式会社 / (株） / ...)."""
    t = base_normalize(s)
    for form in _JP_FORMS:
        t = t.replace(form.casefold(), " ")
    return t


# Readings of the common legal forms, for furigana-side comparisons.
_KANA_LEGAL_READINGS = [
    "カブシキガイシャ", "ユウゲンガイシャ", "ゴウドウガイシャ",
    "ガッコウホウジン", "イリョウホウジン", "シャカイフクシホウジン",
    "イッパンシャダンホウジン", "イッパンザイダンホウジン",
    "コウエキシャダンホウジン", "コウエキザイダンホウジン",
]


def kana_core(s):
    """A name with legal forms removed, kana-folded (kanji kept as-is).
    Kana readings of legal forms are stripped BEFORE the small-kana
    unification inside kana_fold (which would turn シャ into シヤ and
    hide the reading)."""
    t = strip_jp_legal(s)
    t = t.translate({c: chr(c + 0x60) for c in range(0x3041, 0x3097)})
    for r in _KANA_LEGAL_READINGS:      # fully-kana spellings of legal forms
        t = t.replace(r, "")
    return kana_fold(t)


def is_kana_only(s):
    """True when the name (legal forms/punctuation removed) is written
    entirely in katakana — e.g. a kana rendering of a kanji company name."""
    t = kana_core(s)
    if not t:
        return False
    return all(0x30A1 <= ord(c) <= 0x30F6 or c == "ー" for c in t)


# ---------------------------------------------------------------------------
# Learned alias dictionary (B): pairs a human registered as the same
# company. Stored as raw display strings; lookup uses a light cleanup.
# ---------------------------------------------------------------------------
def _alias_key(s):
    """Light cleanup for dictionary lookups: NFKC + case-fold + collapsed
    whitespace. Storage keeps the raw strings exactly as typed/shown."""
    return re.sub(r"\s+", " ", base_normalize(s)).strip()


class AliasDictionary:
    """Unordered pairs of raw company-name strings a human confirmed to
    be the same company, each with a source note and registration date.

    JSON format: {"version": 1, "entries": [{"a", "b", "source",
    "number", "date"}]} — source is "manual" or "houjin" (the latter
    carries the corporate number in "number").
    """

    def __init__(self, path=None):
        self.path = path
        self.entries = []
        if path and os.path.exists(path):
            self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                d = json.load(fh)
            self.entries = [e for e in d.get("entries", [])
                            if isinstance(e, dict) and e.get("a") and e.get("b")]
        except Exception:
            self.entries = []
        return self.entries

    def save(self):
        if not self.path:
            return
        folder = os.path.dirname(self.path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "entries": self.entries}, fh,
                      ensure_ascii=False, indent=1)

    def _find(self, ka, kb):
        for i, e in enumerate(self.entries):
            ea, eb = _alias_key(e["a"]), _alias_key(e["b"])
            if (ea == ka and eb == kb) or (ea == kb and eb == ka):
                return i
        return None

    def has(self, a, b):
        if not _alias_key(a) or not _alias_key(b):
            return False
        return self._find(_alias_key(a), _alias_key(b)) is not None

    def entry(self, a, b):
        i = self._find(_alias_key(a), _alias_key(b))
        return self.entries[i] if i is not None else None

    def add(self, a, b, source="manual", number=None):
        """Register a pair. Returns True when a new entry was created.
        Re-adding an existing pair only fills in a corporate number."""
        a, b = str(a), str(b)
        if not _alias_key(a) or not _alias_key(b) or _alias_key(a) == _alias_key(b):
            return False
        i = self._find(_alias_key(a), _alias_key(b))
        if i is not None:
            if number and not self.entries[i].get("number"):
                self.entries[i]["number"] = str(number)
                self.entries[i]["source"] = source
            return False
        self.entries.append({
            "a": a, "b": b, "source": source,
            "number": str(number) if number else None,
            "date": date.today().isoformat(),
        })
        return True

    def remove(self, a, b):
        i = self._find(_alias_key(a), _alias_key(b))
        if i is None:
            return False
        del self.entries[i]
        return True

    def partners(self, name):
        k = _alias_key(name)
        out = []
        for e in self.entries:
            if _alias_key(e["a"]) == k:
                out.append(e["b"])
            elif _alias_key(e["b"]) == k:
                out.append(e["a"])
        return out


class CompanyEquivalence:
    """Company-name equality used by matching: names are equal when they
    are equal after the deterministic normalization pipeline, OR when a
    human registered the pair in the alias dictionary. Nothing else is
    ever treated as equal (no similarity, ever).

    Dictionary clusters (transitive closures of registered pairs) share
    one canonical key, so dict-paired names behave exactly like
    normalization-equal names in every matching phase.
    """

    def __init__(self, dictionary=None):
        self.dictionary = dictionary
        self._canon = {}          # _alias_key -> canonical comparison key
        if dictionary:
            parent, exemplar = {}, {}

            def find(x):
                parent.setdefault(x, x)
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            for e in dictionary.entries:
                ka, kb = _alias_key(e["a"]), _alias_key(e["b"])
                exemplar.setdefault(ka, e["a"])
                exemplar.setdefault(kb, e["b"])
                ra, rb = find(ka), find(kb)
                if ra != rb:
                    parent[ra] = rb
            clusters = {}
            for k in exemplar:
                clusters.setdefault(find(k), []).append(k)
            for members in clusters.values():
                canon = min(normalize_company(exemplar[m]) for m in members)
                for m in members:
                    self._canon[m] = canon

    def canonical(self, raw):
        ak = _alias_key(raw)
        if ak in self._canon:
            return self._canon[ak]
        return normalize_company(raw)

    def dict_number(self, a, b):
        """Corporate number recorded for this exact dictionary pair."""
        if not self.dictionary:
            return None
        e = self.dictionary.entry(a, b)
        return e.get("number") if e else None


def normalize_text(s):
    """Generic text comparison key."""
    t = base_normalize(s)
    t = re.sub(r"[\s\-_.,/\\()\[\]{}'\"&・:;]+", "", t)
    return t.translate(_SMALL_KANA)


def normalize_code(s):
    """Code/ID comparison key: width/case/hyphens absorbed."""
    t = base_normalize(s).upper()
    return re.sub(r"[\s\-_]+", "", t)


# ---------------------------------------------------------------------------
# Header concepts & mapping proposal
# ---------------------------------------------------------------------------
CONCEPTS = {
    "order_no": ["注文番号", "発注番号", "受注番号", "オーダー番号", "注文書番号",
                 "注文コード", "注文id", "注文no", "オーダーno", "orderno",
                 "ordernumber", "orderid", "ponumber", "purchaseorder", "po"],
    "invoice_no": ["請求番号", "請求書番号", "伝票番号", "納品番号", "伝票no",
                   "invoiceno", "invoicenumber", "invoiceid", "slipno"],
    "company": ["会社名", "取引先", "取引先名", "仕入先", "仕入先名", "顧客名",
                "得意先", "得意先名", "納品先", "発注先", "相手先", "名称",
                "company", "companyname", "vendor", "supplier", "customer",
                "client", "partner", "name", "businesspartner"],
    "amount": ["金額", "請求額", "請求金額", "入金額", "支払額", "合計金額",
               "税込金額", "納品金額", "金額円", "amount", "total", "price",
               "totalamount", "sum"],
    "quantity": ["数量", "個数", "在庫数", "棚卸数", "実在庫数", "数量個",
                 "qty", "quantity", "count", "units", "stock"],
    "date": ["日付", "納品日", "請求日", "発注日", "受注日", "出荷日", "入金日",
             "date", "day"],
    "product": ["商品名", "品名", "品目", "商品", "製品名", "item", "product",
                "商品コード", "品番", "型番", "sku", "itemcode", "productcode"],
}
KEY_CONCEPTS = ("order_no", "invoice_no", "company", "product")
COMPARE_CONCEPTS = ("amount", "quantity")


def header_concept(header):
    h = normalize_text(header)
    if not h:
        return None
    for concept, names in CONCEPTS.items():
        if h in names:
            return concept
    for concept, names in CONCEPTS.items():
        for n in names:
            if len(n) >= 3 and (n in h or h in n):
                return concept
    return None


# ---------------------------------------------------------------------------
# Typed column-name resolution (key/compare setup: what a person types by
# hand must still find the column they mean)
# ---------------------------------------------------------------------------
_HEADER_SEPARATORS = re.compile(
    r"[\s\-‐‑‒–—―−－_＿/／\\＼・･.,、。，:：;；()\[\]{}（）「」『』【】<>＜＞"
    r"'\"’‘“”`&＆+＋*＊#＃@＠!！?？%％~〜^＾|｜=＝]+")


def header_key(s):
    """Aggressive comparison key for a header, stored or typed by hand:
    NFKC width folding + case-folding, the katakana long-vowel mark and
    small kana unified, and every space / punctuation separator dropped.
    '注文　番号', 'Order-No.' and 'ＯＲＤＥＲ番号' fold predictably."""
    t = base_normalize(s)
    t = t.replace("ー", "")
    t = t.translate(_SMALL_KANA)
    return _HEADER_SEPARATORS.sub("", t)


_SYNONYM_KEYS = None


def _synonym_keys():
    """header_key(synonym) -> concept, for every known header synonym."""
    global _SYNONYM_KEYS
    if _SYNONYM_KEYS is None:
        m = {}
        for concept, names in CONCEPTS.items():
            for n in names:
                m.setdefault(header_key(n), concept)
        _SYNONYM_KEYS = m
    return _SYNONYM_KEYS


def _concept_of_typed(text):
    """Best-effort header concept for free-typed text: full text first,
    then its latin / non-latin fragments (so 'ＯＲＤＥＲ番号' and
    'オーダーNo' still land on the order-number concept)."""
    concept = header_concept(text)
    if concept:
        return concept
    concept = _synonym_keys().get(header_key(text))
    if concept:
        return concept
    frags = re.findall(r"[a-z0-9]+|[^\s\x00-\x7f]+", base_normalize(text))
    for frag in sorted(frags, key=len, reverse=True):
        if len(frag) < 2:
            continue
        concept = header_concept(frag) or _synonym_keys().get(header_key(frag))
        if concept:
            return concept
    return None


def resolve_column(table, text):
    """Resolve a typed column name to a column index of `table`, or None.

    Order: exact header -> normalized header (width/case/spaces/
    punctuation absorbed) -> header-concept synonym. Empty or
    unresolvable text returns None; the caller decides whether empty
    means 'unused' (optional rows) and must warn on unresolvable text.
    The typed text itself is never rewritten anywhere.
    """
    if text is None:
        return None
    text = str(text)
    if not text.strip():
        return None
    for i, h in enumerate(table.headers):
        if h == text:
            return i
    key = header_key(text)
    if key:
        for i, h in enumerate(table.headers):
            if header_key(h) == key:
                return i
    concept = _concept_of_typed(text)
    if concept:
        for i, h in enumerate(table.headers):
            if header_concept(h) == concept:
                return i
    return None


def column_kind(values):
    """'number' if >=60% of non-empty values parse as numbers."""
    vals = [v for v in values if str(v).strip()]
    if not vals:
        return "text"
    nums = sum(1 for v in vals if parse_number(v) is not None)
    return "number" if nums / len(vals) >= 0.6 else "text"


def _norm_for_column(values, concept):
    kind = column_kind(values)
    if kind == "number":
        def f(v):
            d = parse_number(v)
            return ("n", d) if d is not None else ("t", normalize_text(v))
        return f
    if concept == "company":
        return lambda v: ("t", normalize_company(v))
    return lambda v: ("t", normalize_code(v) if concept in KEY_CONCEPTS
                      else normalize_text(v))


def _col_values(table, idx):
    return [r[idx] if idx < len(r) else "" for r in table.rows]


def propose_mapping(table_a, table_b):
    """Propose (key_pairs, compare_pairs) of column indexes.

    Scoring: same header concept, identical normalized header, and the
    fraction of values shared between the two columns (value overlap).
    """
    scored = []
    for ai, ha in enumerate(table_a.headers):
        ca = header_concept(ha)
        na = _norm_for_column(_col_values(table_a, ai), ca)
        set_a = {na(v) for v in _col_values(table_a, ai) if str(v).strip()}
        for bi, hb in enumerate(table_b.headers):
            cb = header_concept(hb)
            score = 0.0
            if ca and ca == cb:
                score += 50
            if normalize_text(ha) and normalize_text(ha) == normalize_text(hb):
                score += 40
            nb = _norm_for_column(_col_values(table_b, bi), cb)
            set_b = {nb(v) for v in _col_values(table_b, bi) if str(v).strip()}
            if set_a and set_b:
                overlap = len(set_a & set_b) / min(len(set_a), len(set_b))
                score += overlap * 50
            else:
                overlap = 0.0
            if score > 0:
                scored.append((score, ai, bi, overlap))
    scored.sort(key=lambda x: -x[0])
    used_a, used_b, pairs = set(), set(), []
    for score, ai, bi, overlap in scored:
        if ai in used_a or bi in used_b:
            continue
        used_a.add(ai)
        used_b.add(bi)
        pairs.append((ai, bi, score, overlap))
    # keys: concept-strong or high-overlap pairs first, up to 2
    def key_rank(p):
        ai, bi, score, overlap = p
        c = header_concept(table_a.headers[ai]) or header_concept(table_b.headers[bi])
        return (0 if c in KEY_CONCEPTS else 1, -overlap, -score)
    def _key_ok(p):
        ca = header_concept(table_a.headers[p[0]])
        cb = header_concept(table_b.headers[p[1]])
        if ca in KEY_CONCEPTS or cb in KEY_CONCEPTS:
            return True
        # amount/quantity-like columns are compare targets, never keys
        if ca in COMPARE_CONCEPTS or cb in COMPARE_CONCEPTS:
            return False
        return p[3] >= 0.5     # unknown headers: only on strong value overlap

    key_candidates = [p for p in pairs if _key_ok(p)]
    key_candidates.sort(key=key_rank)
    keys = [(ai, bi) for ai, bi, _, _ in key_candidates[:2]]
    key_set = set(keys)
    compares = []
    for ai, bi, score, overlap in pairs:
        if (ai, bi) in key_set:
            continue
        ca = header_concept(table_a.headers[ai])
        cb = header_concept(table_b.headers[bi])
        kind_a = column_kind(_col_values(table_a, ai))
        kind_b = column_kind(_col_values(table_b, bi))
        if kind_a == "number" and kind_b == "number" and (
                ca in COMPARE_CONCEPTS or cb in COMPARE_CONCEPTS or overlap >= 0.2):
            compares.append((ai, bi))
        if len(compares) >= 3:
            break
    return keys, compares


# ---------------------------------------------------------------------------
# Reconciliation engine
# ---------------------------------------------------------------------------
class Candidate:
    def __init__(self, cid, kind, a_rows, b_rows, confidence,
                 reason_key, reason_params=None):
        self.id = cid
        self.kind = kind                    # 'name' | 'group'
        self.a_rows = a_rows                # list[int]
        self.b_rows = b_rows                # list[int]
        # Candidates are deterministic (exactly equal after normalization,
        # or an exact sum) — there is no probability score: confidence
        # stays None and the UI shows the reason only.
        self.confidence = confidence
        self.reason_key = reason_key
        self.reason_params = reason_params or {}
        self.status = "pending"             # pending | accepted | rejected


class DiffPair:
    def __init__(self, a, b, diffs, origin="exact"):
        self.a = a
        self.b = b
        self.diffs = diffs                  # [{ca, cb, va, vb, da, db}]
        self.origin = origin                # exact | name | manual


class ReconResult:
    def __init__(self, table_a, table_b, config):
        self.table_a = table_a
        self.table_b = table_b
        self.config = config
        self.ok_pairs = []                  # [(ai, bi)]
        self.diff_pairs = []                # [DiffPair]
        self.candidates = []                # [Candidate]
        self.houjin_pairs = []              # [(ai, bi, corporate_number)]
        self.group_capped = False
        self._matched_a = set()
        self._matched_b = set()

    # -- membership ------------------------------------------------------
    def _cand_rows(self, side):
        rows = set()
        for c in self.candidates:
            if c.status in ("pending", "accepted"):
                rows.update(c.a_rows if side == "a" else c.b_rows)
        return rows

    def cat1_a(self):
        used = self._matched_a | self._cand_rows("a")
        return [i for i in range(len(self.table_a.rows)) if i not in used]

    def cat1_b(self):
        used = self._matched_b | self._cand_rows("b")
        return [i for i in range(len(self.table_b.rows)) if i not in used]

    def counts(self):
        return {
            "total_a": len(self.table_a.rows),
            "total_b": len(self.table_b.rows),
            "ok": len(self.ok_pairs),
            "diff": len(self.diff_pairs),
            "cat1_a": len(self.cat1_a()),
            "cat1_b": len(self.cat1_b()),
            "cat3": sum(1 for c in self.candidates if c.status == "pending"),
        }

    # -- human decisions ---------------------------------------------------
    def _compare_pair(self, ai, bi):
        diffs = compare_rows(self.table_a, self.table_b, ai, bi,
                             self.config["compare_pairs"], self.config["tolerance"])
        return diffs

    def accept(self, cid):
        cand = next((c for c in self.candidates if c.id == cid), None)
        if cand is None or cand.status != "pending":
            return False
        cand.status = "accepted"
        if cand.kind == "name":
            ai, bi = cand.a_rows[0], cand.b_rows[0]
            self._matched_a.add(ai)
            self._matched_b.add(bi)
            diffs = self._compare_pair(ai, bi)
            if diffs:
                self.diff_pairs.append(DiffPair(ai, bi, diffs, origin="name"))
            else:
                self.ok_pairs.append((ai, bi))
        else:  # group: sums match by construction -> all rows matched
            for ai in cand.a_rows:
                self._matched_a.add(ai)
            for bi in cand.b_rows:
                self._matched_b.add(bi)
            anchor_a = cand.a_rows[0] if len(cand.a_rows) == 1 else None
            anchor_b = cand.b_rows[0] if len(cand.b_rows) == 1 else None
            if anchor_a is not None and anchor_b is not None:
                self.ok_pairs.append((anchor_a, anchor_b))
        return True

    def reject(self, cid):
        cand = next((c for c in self.candidates if c.id == cid), None)
        if cand is None or cand.status != "pending":
            return False
        cand.status = "rejected"   # rows fall back to category 1
        return True

    def manual_pair(self, ai, bi):
        if ai not in self.cat1_a() or bi not in self.cat1_b():
            return False
        self._matched_a.add(ai)
        self._matched_b.add(bi)
        diffs = self._compare_pair(ai, bi)
        if diffs:
            self.diff_pairs.append(DiffPair(ai, bi, diffs, origin="manual"))
        else:
            self.ok_pairs.append((ai, bi))
        return True

    def houjin_pair(self, ai, bi, number):
        """Pair two category-1 rows on registry-proven identity (same
        corporate number; see houjin.evaluate). Records the number so
        the UI/report can show the proof."""
        if ai not in self.cat1_a() or bi not in self.cat1_b():
            return False
        self._matched_a.add(ai)
        self._matched_b.add(bi)
        diffs = self._compare_pair(ai, bi)
        if diffs:
            self.diff_pairs.append(DiffPair(ai, bi, diffs, origin="houjin"))
        else:
            self.ok_pairs.append((ai, bi))
        self.houjin_pairs.append((ai, bi, str(number)))
        return True


def compare_rows(table_a, table_b, ai, bi, compare_pairs, tolerance):
    diffs = []
    for ca, cb in compare_pairs:
        va_raw = table_a.rows[ai][ca] if ca < len(table_a.rows[ai]) else ""
        vb_raw = table_b.rows[bi][cb] if cb < len(table_b.rows[bi]) else ""
        da, db = parse_number(va_raw), parse_number(vb_raw)
        if da is None or db is None:
            if normalize_text(va_raw) != normalize_text(vb_raw):
                diffs.append({"ca": ca, "cb": cb, "va": va_raw, "vb": vb_raw,
                              "da": da, "db": db})
            continue
        if abs(da - db) > tolerance:
            diffs.append({"ca": ca, "cb": cb, "va": va_raw, "vb": vb_raw,
                          "da": da, "db": db})
    return diffs


def reconcile(table_a, table_b, key_pairs, compare_pairs,
              tolerance=Decimal("0"), equiv=None):
    """Run the full pipeline. Returns a ReconResult.

    Matching is deterministic only: rows pair when their keys are equal
    after normalization, and category-3 candidates are pairs whose
    counterpart name becomes exactly equal after normalization, or whose
    amounts sum exactly. Similar-but-unequal names are NEVER paired or
    suggested — a wrong-company suggestion is a source of mistakes.

    `equiv` (a CompanyEquivalence) may add human-registered dictionary
    pairs to company-name equality; it never adds anything else.
    """
    if isinstance(tolerance, (int, float, str)):
        tolerance = Decimal(str(tolerance))
    if equiv is None:
        equiv = CompanyEquivalence()
    config = {"key_pairs": key_pairs, "compare_pairs": compare_pairs,
              "tolerance": tolerance}
    res = ReconResult(table_a, table_b, config)
    if not key_pairs:
        return res
    # per-key-column normalizers (decided on table A's column, mirrored for B)
    norm_a, norm_b = [], []
    for ai, bi in key_pairs:
        ca = header_concept(table_a.headers[ai])
        cb = header_concept(table_b.headers[bi])
        concept = ca or cb
        if concept == "company":
            # company columns: deterministic normalization + dictionary
            norm_a.append(lambda v: ("t", equiv.canonical(v)))
            norm_b.append(lambda v: ("t", equiv.canonical(v)))
        else:
            norm_a.append(_norm_for_column(_col_values(table_a, ai), concept))
            norm_b.append(_norm_for_column(_col_values(table_b, bi), concept))

    def key_of(table, idx, norms, side_pairs):
        row = table.rows[idx]
        out = []
        for k, (ai, bi) in enumerate(side_pairs):
            ci = ai if norms is norm_a else bi
            v = row[ci] if ci < len(row) else ""
            out.append(norms[k](v))
        return tuple(out)

    groups_a, groups_b = {}, {}
    for i in range(len(table_a.rows)):
        groups_a.setdefault(key_of(table_a, i, norm_a, key_pairs), []).append(i)
    for i in range(len(table_b.rows)):
        groups_b.setdefault(key_of(table_b, i, norm_b, key_pairs), []).append(i)

    # (a)+(b) exact matching: equal-compare pairs first, then positional
    # pairs for the difference category when group sizes line up; uneven
    # leftovers stay single so the group-sum phase can use them.
    for key, a_list in groups_a.items():
        b_list = groups_b.get(key)
        if not b_list:
            continue
        rem_a, rem_b = list(a_list), list(b_list)
        for ai in list(rem_a):
            hit = None
            for bi in rem_b:
                if not compare_rows(table_a, table_b, ai, bi,
                                    compare_pairs, tolerance):
                    hit = bi
                    break
            if hit is not None:
                rem_a.remove(ai)
                rem_b.remove(hit)
                res._matched_a.add(ai)
                res._matched_b.add(hit)
                res.ok_pairs.append((ai, hit))
        if len(rem_a) == len(rem_b):
            for ai, bi in zip(rem_a, rem_b):
                res._matched_a.add(ai)
                res._matched_b.add(bi)
                diffs = compare_rows(table_a, table_b, ai, bi,
                                     compare_pairs, tolerance)
                if diffs:
                    res.diff_pairs.append(DiffPair(ai, bi, diffs, origin="exact"))
                else:
                    res.ok_pairs.append((ai, bi))

    singles_a = [i for i in range(len(table_a.rows)) if i not in res._matched_a]
    singles_b = [i for i in range(len(table_b.rows)) if i not in res._matched_b]

    # name source for group/name phases: company-concept key column,
    # else the first key column
    name_k = 0
    for k, (ai, bi) in enumerate(key_pairs):
        if (header_concept(table_a.headers[ai]) == "company"
                or header_concept(table_b.headers[bi]) == "company"):
            name_k = k
            break

    def name_raw(table, idx, side):
        ai, bi = key_pairs[name_k]
        ci = ai if side == "a" else bi
        row = table.rows[idx]
        return row[ci] if ci < len(row) else ""

    def name_norm(table, idx, side):
        return equiv.canonical(name_raw(table, idx, side))

    names_a = {i: name_norm(table_a, i, "a") for i in singles_a}
    names_b = {i: name_norm(table_b, i, "b") for i in singles_b}
    raw_a = {i: name_raw(table_a, i, "a") for i in singles_a}
    raw_b = {i: name_raw(table_b, i, "b") for i in singles_b}

    cid = [0]

    def next_cid():
        cid[0] += 1
        return cid[0]

    # (e) grouped-sum candidates (before the name phase: an exact sum
    # match on the exactly-equal counterpart is checked first) ------------
    consumed_a, consumed_b = set(), set()
    if compare_pairs:
        amt_a, amt_b = compare_pairs[0]

        def amount(table, idx, col):
            row = table.rows[idx]
            return parse_number(row[col]) if col < len(row) else None

        def find_groups(one_rows, one_names, other_rows, other_names,
                        one_side):
            found = []
            other_by_name = {}
            for i in other_rows:
                if other_names[i]:
                    other_by_name.setdefault(other_names[i], []).append(i)
            for oi in one_rows:
                nm = one_names[oi]
                if not nm or nm not in other_by_name:
                    continue
                group = other_by_name[nm]
                target = amount(table_a if one_side == "a" else table_b,
                                oi, amt_a if one_side == "a" else amt_b)
                if target is None:
                    continue
                if len(group) > 20:
                    res.group_capped = True
                    group = group[:20]
                vals = [(gi, amount(table_b if one_side == "a" else table_a,
                                    gi, amt_b if one_side == "a" else amt_a))
                        for gi in group]
                vals = [(gi, v) for gi, v in vals if v is not None]
                hit = None
                for size in (2, 3):
                    for combo in itertools.combinations(vals, size):
                        if abs(sum(v for _, v in combo) - target) <= tolerance:
                            hit = [gi for gi, _ in combo]
                            break
                    if hit:
                        break
                if hit:
                    found.append((oi, hit))
            return found

        for oi, hit in find_groups(singles_a, names_a, singles_b, names_b, "a"):
            if oi in consumed_a or any(h in consumed_b for h in hit):
                continue
            consumed_a.add(oi)
            consumed_b.update(hit)
            res.candidates.append(Candidate(
                next_cid(), "group", [oi], hit, None, "reason_group",
                {"count": len(hit)}))
        rest_a2 = [i for i in singles_a if i not in consumed_a]
        rest_b2 = [i for i in singles_b if i not in consumed_b]
        names_a2 = {i: names_a[i] for i in rest_a2}
        for oi, hit in find_groups(rest_b2,
                                   {i: names_b[i] for i in rest_b2},
                                   rest_a2, names_a2, "b"):
            if oi in consumed_b or any(h in consumed_a for h in hit):
                continue
            consumed_b.add(oi)
            consumed_a.update(hit)
            res.candidates.append(Candidate(
                next_cid(), "group", hit, [oi], None, "reason_group",
                {"count": len(hit)}))

    # (d) deterministic name-equal candidates on what is left --------------
    # The counterpart names must become EXACTLY equal after the
    # deterministic normalization pipeline (legal-form stripping, width /
    # case / punctuation / space folding, kana folding). There is no
    # similarity scoring anywhere: a name that is merely similar stays in
    # category 1 for the human to pair by hand if it really is the same.
    rest_a = [i for i in singles_a if i not in consumed_a]
    rest_b = [i for i in singles_b if i not in consumed_b]
    b_by_name = {}
    for i in rest_b:
        if names_b[i]:
            b_by_name.setdefault(names_b[i], []).append(i)
    for ai in rest_a:
        nm = names_a[ai]
        if not nm or not b_by_name.get(nm):
            continue
        bi = b_by_name[nm].pop(0)
        # Why are they equal? Plain normalization, or a dictionary pair a
        # human registered (the reason shown must say which).
        if normalize_company(raw_a[ai]) and \
                normalize_company(raw_a[ai]) == normalize_company(raw_b[bi]):
            rk, rp = "reason_legal", {}
        else:
            num = equiv.dict_number(raw_a[ai], raw_b[bi])
            if num:
                rk, rp = "reason_dict_num", {"number": num}
            else:
                rk, rp = "reason_dict", {}
        res.candidates.append(Candidate(
            next_cid(), "name", [ai], [bi], None, rk, rp))
    return res

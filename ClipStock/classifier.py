# -*- coding: utf-8 -*-
"""
ClipStock - deterministic text classifier for copied text.

Every copied text is sorted into exactly one kind using ONLY deterministic
patterns (regular expressions and fixed character rules, evaluated in the
fixed order below). No fuzzy matching, no similarity scoring, no machine
learning - this follows the user's all-apps rule.

Kinds: url / email / amount / date / address / code / other

classify(text) -> (kind, reason_key)
  reason_key is a key suffix used with i18n ("reason_" + reason_key) so the
  UI can show WHY the text was classified that way, in the user's language.

Decision order (first match wins):
  0. empty / multi-line / very long text        -> other
  1. URL      (http://, https://, www. ...)
  2. Email    (local@domain.tld, whole string)
  3. Amount   (currency symbol / unit / thousands separators)
  4. Date     (numeric dates, Japanese dates, times)
  5. Address  (Japanese prefecture pattern / English street suffix)
  6. Code     (letter+digit mix / digit sequences with separators)
  7. other

is_sensitive(text) -> reason_key or None
  Deterministic "looks secret" checks used by the privacy filter:
  - a 13-19 digit sequence (spaces / hyphens allowed) that passes Luhn
  - a leading "password:" / "passwd=" style label
"""
import re

MAX_CLASSIFY_LEN = 500

# --- 1. URL -------------------------------------------------------------
_RE_URL = re.compile(r"^(https?://|www\.)\S+$", re.IGNORECASE)

# --- 2. Email -----------------------------------------------------------
_RE_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# --- 3. Amount ----------------------------------------------------------
_CURRENCY_SYMBOLS = "¥$€£₹₽"
_CURRENCY_UNITS = (
    "円|ドル|ユーロ|ポンド|元|ウォン|フラン|ルーブル|レアル|ペソ|"
    "USD|JPY|EUR|GBP|CNY|KRW|CHF|INR|RUB|BRL|MXN|TRY|AED"
)
_RE_AMOUNT_SYMBOL = re.compile(
    r"^[" + _CURRENCY_SYMBOLS + r"]\s?\d[\d,]*(\.\d+)?$")
_RE_AMOUNT_UNIT = re.compile(
    r"^\d[\d,]*(\.\d+)?\s?(" + _CURRENCY_UNITS + r")$")
_RE_AMOUNT_THOUSANDS = re.compile(r"^\d{1,3}(,\d{3})+(\.\d+)?$")

# --- 4. Date / time -----------------------------------------------------
_RE_DATE_ISO = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$")
_RE_DATE_JP = re.compile(r"^\d{4}年\d{1,2}月\d{1,2}日$")
_RE_DATE_DMY = re.compile(r"^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$")
_RE_DATETIME = re.compile(
    r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}(:\d{2})?$")
_RE_TIME = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")

# --- 5. Address ---------------------------------------------------------
_RE_POSTAL_JP = re.compile(r"^〒?\s?\d{3}-\d{4}")
_RE_PREF = re.compile(r"(東京都|北海道|(?:京都|大阪)府|[^\s]{2,3}県)")
_RE_CITY = re.compile(r"[^\s]{1,6}(市|区|町|村)")
_RE_BANCHI = re.compile(r"(\d+丁目|\d+[-−]\d+|\d+番地)")
_RE_STREET_EN = re.compile(
    r"\b(Street|St\.|Avenue|Ave\.|Road|Rd\.|Boulevard|Blvd\.|"
    r"Lane|Ln\.|Drive|Dr\.|Court|Ct\.)\b", re.IGNORECASE)
_RE_HAS_DIGIT = re.compile(r"\d")

# --- 6. Code ------------------------------------------------------------
_RE_CODE_MIXED = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_/]{2,}$")
_RE_CODE_DIGITS = re.compile(r"^\d[\d\-]{5,}\d$")


def _is_japanese_address(s):
    """Deterministic JP address shape: prefecture + municipality + number.
    A bare digit-hyphen sequence (e.g. a phone number) must NOT match the
    postal-code rule: the postal prefix only counts when it carries the
    〒 mark or is followed by an actual address element."""
    if s.startswith("〒") and _RE_POSTAL_JP.match(s):
        return True
    m = _RE_POSTAL_JP.match(s)
    if m and (_RE_PREF.search(s) or _RE_CITY.search(s)):
        return True
    if _RE_PREF.search(s) and _RE_CITY.search(s) and _RE_BANCHI.search(s):
        return True
    return False


def _is_english_address(s):
    """English address shape: street suffix word plus a house number digit,
    and at least two words (a bare product name cannot match)."""
    return bool(_RE_STREET_EN.search(s) and _RE_HAS_DIGIT.search(s)
                and " " in s)


def classify(text):
    """Return (kind, reason_key). See module docstring for the order."""
    if text is None:
        return "other", "other"
    s = text.strip()
    if not s:
        return "other", "other"
    if "\n" in s or "\r" in s:
        return "other", "multiline"
    if len(s) > MAX_CLASSIFY_LEN:
        return "other", "long"

    # 1. URL
    if _RE_URL.match(s):
        return "url", "url"
    # 2. Email
    if _RE_EMAIL.match(s):
        return "email", "email"
    # 3. Amount
    if _RE_AMOUNT_SYMBOL.match(s):
        return "amount", "amount_symbol"
    if _RE_AMOUNT_UNIT.match(s):
        return "amount", "amount_unit"
    if _RE_AMOUNT_THOUSANDS.match(s):
        return "amount", "amount_thousands"
    # 4. Date / time
    if (_RE_DATETIME.match(s) or _RE_DATE_ISO.match(s)
            or _RE_DATE_JP.match(s) or _RE_DATE_DMY.match(s)):
        return "date", "date"
    if _RE_TIME.match(s):
        return "date", "time"
    # 5. Address
    if _is_japanese_address(s):
        return "address", "address_jp"
    if _is_english_address(s):
        return "address", "address_en"
    # 6. Code
    if _RE_CODE_MIXED.match(s):
        has_letter = any(c.isalpha() for c in s)
        has_digit = any(c.isdigit() for c in s)
        if has_letter and has_digit:
            return "code", "code_mixed"
    if _RE_CODE_DIGITS.match(s):
        digits = sum(c.isdigit() for c in s)
        if digits >= 7:
            return "code", "code_digits"
    # 7. Fallback
    return "other", "other"


def luhn_ok(digits):
    """Standard Luhn checksum over a string of decimal digits."""
    if not digits or not digits.isdigit():
        return False
    total = 0
    alt = False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


_RE_DIGIT_SEQ = re.compile(r"\d[\d \-]{11,}\d")
_RE_SECRET_LABEL = re.compile(
    r"^(password|passwd|pwd|パスワード|暗証番号)\s*[:：=]", re.IGNORECASE)


def is_sensitive(text):
    """Return a reason key ('card' / 'secret_label') or None.

    Only deterministic shapes are treated as sensitive: a digit sequence
    that passes the Luhn check (payment-card shape), or an explicit
    password-style label at the start of the text.
    """
    if text is None:
        return None
    s = text.strip()
    if not s or "\n" in s:
        return None
    if _RE_SECRET_LABEL.match(s):
        return "secret_label"
    for m in _RE_DIGIT_SEQ.finditer(s):
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            return "card"
    return None

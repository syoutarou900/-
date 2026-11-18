# -*- coding: utf-8 -*-
"""Deterministic normalization for UniList.

Every comparison in this app is EXACT equality after the deterministic
normalization in this module. There is NO similarity / fuzzy matching
anywhere (no difflib, no Levenshtein): two values are candidates only
when their normalized keys are identical strings.

The legal-form tables are reused from MatchDetective (same project
family, same deterministic approach).
"""
import hashlib
import re
import unicodedata

_SMALL_KANA = str.maketrans("ァィゥェォッャュョヮヵヶ", "アイウエオツヤユヨワカケ")
_HIRA_TO_KATA = {c: chr(c + 0x60) for c in range(0x3041, 0x3097)}


def base_normalize(s):
    """NFKC (fullwidth->halfwidth, halfwidth kana->fullwidth,
    ㈱->(株) ...) plus case-folding."""
    if s is None:
        return ""
    return unicodedata.normalize("NFKC", str(s)).casefold()


def fold_latin_accents(t):
    """Fold Latin accents (é->e, ü->u, ñ->n) deterministically.

    Only characters in the Latin ranges are decomposed and stripped of
    combining marks; other scripts (Japanese kana dakuten etc.) are
    left untouched."""
    out = []
    for ch in t:
        if ord(ch) < 0x250:
            d = unicodedata.normalize("NFD", ch)
            out.append("".join(c for c in d
                               if unicodedata.category(c) != "Mn"))
        else:
            out.append(ch)
    return "".join(out)


# --- legal-entity forms (reused from MatchDetective) -------------------------
_JP_FORMS = ["株式会社", "有限会社", "合同会社", "合名会社", "合資会社",
             "一般社団法人", "一般財団法人", "公益社団法人", "公益財団法人",
             "医療法人", "学校法人", "社会福祉法人", "特定非営利活動法人",
             "(株)", "(有)", "（株）", "（有）", "(同)", "（同）"]
_KR_FORMS = ["주식회사", "(주)", "유한회사", "유한책임회사", "합자회사", "합명회사",
             "(유)", "(합)"]
_CN_FORMS = ["股份有限公司", "有限责任公司", "有限公司"]
_AR_FORMS = ["شركة ذات مسؤولية محدودة", "ذات مسؤولية محدودة",
             "شركة مساهمة", "مؤسسة فردية", "ذ.م.م", "ذ م م",
             "ش.م.م", "ش م م", "شركة", "مؤسسة"]
_TR_FORMS = ["limited şirketi", "ltd. şti.", "ltd. sti.", "koll. şti.",
             "kom. şti.", "a.ş.", "a.s.", "şti.", "sti."]
_RU_FORMS = ["ооо", "оао", "пао", "ао", "зао", "ип"]
_LEGAL_TOKENS = {
    "inc", "corp", "corporation", "ltd", "limited", "llc", "llp", "lp",
    "co", "company", "pc", "pty", "pte", "pvt", "bvba",
    "gmbh", "ag", "kg", "kgaa", "ohg", "ek", "ug", "eg",
    "sa", "sas", "sarl", "sl", "srl", "spa", "sca", "lda",
    "bv", "nv", "vof", "cv",
    "ab", "as", "oy", "oyj", "aps", "ehf",
    "ltda", "limitada", "eireli", "epp", "me", "unipessoal",
    "ooo", "pao", "ao", "zao", "ip",
    "pt", "perseroan", "terbatas", "ud", "firma", "fa", "koperasi",
    "sro", "spzoo", "kft", "zrt",
}
_LEGAL_PHRASES = [r"s\.?a\.?\s*de\s*c\.?v\.?", r"s\.?a\.?\s*de\s*c\.?v",
                  r"sdn\.?\s*bhd\.?", r"(?<![a-z])p\.?t\.?(?![a-z])",
                  r"(?<![a-z])c\.?v\.?(?![a-z])", r"(?<![a-z])b\.?v\.?(?![a-z])",
                  r"s\.a\.s\.?", r"s\.a\.r\.l\.?", r"s\.a\.?", r"s\.l\.?",
                  r"s\.r\.l\.?", r"l\.l\.c\.?", r"l\.l\.p\.?", r"p\.l\.c\.?",
                  r"p\.c\.?", r"e\.k\.?", r"s\.c\.a\.?"]


def normalize_name(s):
    """Company / person name comparison key.

    width/case folded, Latin accents folded, legal forms stripped,
    hiragana unified to katakana, small kana unified, and all spaces
    and punctuation removed. Equality of this key is the ONLY way two
    names are considered 'the same name'."""
    t = base_normalize(s)
    t = fold_latin_accents(t)
    # Turkish fold: dotted/dotless i variants merge
    t = t.replace("i̇", "i").replace("ı", "i")
    for form in _JP_FORMS + _KR_FORMS + _CN_FORMS + _AR_FORMS + _TR_FORMS:
        t = t.replace(form.casefold(), " ")
    if re.search(r"[a-zа-яё]", t):
        # Latin/Cyrillic-script names: phrase + token legal-form stripping
        for phrase in _LEGAL_PHRASES:
            t = re.sub(phrase, " ", t)
        for form in _RU_FORMS:
            t = re.sub(r"(?<![0-9a-zа-яё])" + form + r"(?![0-9a-zа-яё])",
                       " ", t)
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
        t = "".join(tok for tok in kept
                    if not (re.fullmatch(r"[0-9a-z]+", tok) is None
                            and not tok.strip("()[]{}.,&・/\\-_'\"«»„“”‚‘’")))
    t = t.translate(_HIRA_TO_KATA)
    t = t.translate(_SMALL_KANA)
    if t.endswith("集团"):
        t = t[:-2]
    # final key: no spaces, no punctuation at all
    t = re.sub(r"[\s\W_]+", "", t, flags=re.UNICODE)
    return t.strip()


# --- phone -------------------------------------------------------------------
# Common country calling codes (for deterministic trunk / CC handling).
_COUNTRY_CODES = [
    "886", "852", "853", "420", "358", "353", "380", "234", "254",
    "81", "82", "86", "44", "33", "49", "61", "91", "55", "34", "39",
    "31", "65", "84", "66", "62", "60", "63", "64", "41", "46", "47",
    "45", "48", "90", "52", "54", "56", "51", "27", "20", "36", "43",
    "32", "30", "351", "7", "1",
]
_EXT_RE = re.compile(r"(?i)(ext\.?|extension|x|内線|;)\s*\d+\s*$")


def phone_keys(s):
    """Return a SET of deterministic keys for a phone number.

    The set always contains the full digit string (country code kept,
    '00' international prefix folded into it). International numbers
    also yield their national significant number (country code
    stripped); domestic numbers also yield their trunk-'0'-stripped
    form. Two numbers match when their key sets intersect - still
    exact string equality, just over the canonical variants."""
    if s is None:
        return set()
    t = unicodedata.normalize("NFKC", str(s)).strip()
    if not t:
        return set()
    t = _EXT_RE.sub("", t)
    international = t.startswith("+") or t.startswith("00")
    digits = re.sub(r"\D", "", t)
    if not digits:
        return set()
    if t.startswith("00"):
        digits = digits[2:]
        international = True
    keys = {digits}
    if international:
        for cc in _COUNTRY_CODES:
            if digits.startswith(cc) and len(digits) > len(cc) + 3:
                keys.add(digits[len(cc):])
                break
    elif digits.startswith("0"):
        keys.add(digits[1:])
    return {k for k in keys if len(k) >= 5}


def normalize_phone(s):
    """Primary (display) phone key: the longest canonical digit form."""
    keys = phone_keys(s)
    if not keys:
        return ""
    return max(keys, key=len)


def normalize_email(s):
    """Email key: width/case folded, spaces removed. Exact match only."""
    t = base_normalize(s)
    return re.sub(r"\s+", "", t).strip()


def normalize_address(s):
    """Address key: width/case folded, Latin accents folded, digits
    unified by NFKC, all spaces and punctuation removed."""
    t = base_normalize(s)
    t = fold_latin_accents(t)
    t = t.translate(_HIRA_TO_KATA)
    t = t.translate(_SMALL_KANA)
    t = re.sub(r"[\s\W_]+", "", t, flags=re.UNICODE)
    return t.strip()


def normalize_id(s):
    """ID key (corporate number, customer code, tax id...): width/case
    folded, spaces and hyphens removed. Exact match only."""
    t = base_normalize(s)
    return re.sub(r"[\s\-‐ー]+", "", t).strip()


def normalize_generic(s):
    """Loose-but-deterministic key used for row signatures:
    width/case fold + whitespace collapse."""
    t = base_normalize(s)
    return re.sub(r"\s+", " ", t).strip()


def row_signature(values):
    """Content-based signature of a row (stable across sessions and
    reloads of the same file). Used for the learned 'not a duplicate'
    pairs so the judgement survives reloading the list."""
    joined = "\x1f".join(normalize_generic(v) for v in values)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()

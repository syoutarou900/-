# -*- coding: utf-8 -*-
"""Check engine for the pre-send checker. Split from core.py (extraction)
to keep files manageable. All comparisons are exact after deterministic
normalization - no fuzzy matching anywhere."""
import datetime
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

from core import (GREEN, YELLOW, RED, LEVEL_ORDER, worst, to_half,
                  extract_amounts, extract_dates, extract_companies,
                  extract_doc_numbers, normalize_company, normalize_docnum,
                  company_tokens, fmt_money, parse_number, Attachment)

CHECK_ORDER = ["attach", "amount", "date", "company", "docnum",
               "domain", "version", "filename", "readable", "ocr"]

FREEMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.co.jp", "yahoo.com", "ymail.com",
    "outlook.com", "outlook.jp", "hotmail.com", "hotmail.co.jp", "live.com",
    "icloud.com", "me.com", "mac.com", "proton.me", "protonmail.com",
    "aol.com", "gmx.com", "gmx.net", "mail.com", "yandex.com", "yandex.ru",
    "qq.com", "163.com", "naver.com", "daum.net", "hanmail.net",
    "docomo.ne.jp", "ezweb.ne.jp", "au.com", "softbank.ne.jp",
    "i.softbank.jp", "nifty.com", "biglobe.ne.jp", "ocn.ne.jp",
}

# country code -> (legacy charset used for the encodability test, name is UI-side)
COUNTRY_CHARSETS = {
    "JP": "shift_jis", "US": "cp1252", "GB": "cp1252", "DE": "cp1252",
    "FR": "cp1252", "ES": "cp1252", "IT": "cp1252", "PT": "cp1252",
    "ID": "cp1252", "CN": "gbk", "KR": "cp949", "RU": "cp1251",
    "TR": "cp1254", "OTHER": "utf-8",
}

ATTACH_WORDS = ("添付", "別添", "別紙", "attached", "attachment", "attach",
                "enclosed", "enclosing", "anhang", "angehängt", "beigefügt",
                "joint", "ci-joint", "adjunto", "anexo", "allegato", "allegati",
                "ekte", "ekinde", "첨부", "附件", "bijgevoegd", "załącznik",
                "приложен", "вложен")
DOC_WORDS = ("見積", "請求", "納品書", "注文書", "invoice", "estimate",
             "quotation", "quote", "proforma", "rechnung", "angebot",
             "facture", "devis", "factura", "presupuesto", "fattura",
             "preventivo", "fatura", "orçamento", "teklif", "견적", "송장",
             "청구", "发票", "报价", "报价单", "счёт", "счет", "коммерческое")


@dataclass
class Finding:
    check: str
    level: str
    reason_key: str
    params: dict = field(default_factory=dict)
    evidence: str = ""


@dataclass
class CheckInput:
    recipients_text: str = ""
    subject: str = ""
    body: str = ""
    attachments: list = field(default_factory=list)   # list[Attachment]
    expected_company: str = ""
    expected_domain: str = ""
    expected_amount: str = ""
    expected_date: str = ""
    expected_docnum: str = ""
    country: str = "JP"
    labels: dict = field(default_factory=lambda: {"body": "Body", "att": "File"})


@dataclass
class Report:
    overall: str
    findings: list
    rename_suggestions: dict = field(default_factory=dict)  # path -> new name

    def by_check(self, check):
        return [f for f in self.findings if f.check == check]


def parse_emails(text):
    return re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
                      to_half(text or ""))


def _domain_of(email_addr):
    return email_addr.rsplit("@", 1)[-1].lower().strip()


def _domain_tokens(domain):
    tokens = set()
    for label in domain.split("."):
        if label in ("co", "com", "net", "org", "jp", "uk", "de", "fr", "io",
                     "ne", "or", "ac", "go", "info", "biz"):
            continue
        for tok in re.split(r"[^a-z0-9]+", label):
            if len(tok) >= 3:
                tokens.add(tok)
    return tokens


def _amounts_summary(amounts, limit=6):
    parts = []
    for a in amounts[:limit]:
        cur = a.currency or ""
        parts.append(f"{cur} {fmt_money(a.value)}".strip())
    return ", ".join(parts)


def _totals_by_currency(amounts):
    totals = {}
    for a in amounts:
        if a.kind == "total":
            totals.setdefault(a.currency, set()).add(a.value)
    return totals


# ---------------------------------------------------------------------------
# individual checks
# ---------------------------------------------------------------------------

def _check_attach(inp, findings):
    body_low = to_half(inp.body).lower()
    mentions_attach = any(w in body_low for w in ATTACH_WORDS)
    mentions_doc = any(w in body_low for w in DOC_WORDS) or \
        any(w in to_half(inp.subject).lower() for w in DOC_WORDS)
    n = len(inp.attachments)
    if n == 0 and (mentions_attach or mentions_doc):
        findings.append(Finding("attach", RED, "r_attach_missing"))
    elif n > 0 and not mentions_attach and not mentions_doc:
        findings.append(Finding("attach", YELLOW, "r_attach_no_mention",
                                {"count": n}))
    elif n == 0:
        findings.append(Finding("attach", YELLOW, "r_attach_none_no_mention"))
    else:
        findings.append(Finding("attach", GREEN, "r_attach_ok", {"count": n}))


def _check_amounts(inp, body_amounts, findings):
    expected = extract_amounts(inp.expected_amount)
    exp_plain = None
    if not expected and inp.expected_amount.strip():
        exp_plain = parse_number(to_half(inp.expected_amount))
    atts = inp.attachments
    if expected or exp_plain is not None:
        exp = expected[0] if expected else None
        exp_val = exp.value if exp else exp_plain
        exp_cur = exp.currency if exp else ""
        targets = [(inp.labels["body"], body_amounts)]
        targets += [(a.name, a.amounts) for a in atts]
        bad = []
        for label, amounts in targets:
            pool = [a for a in amounts
                    if not exp_cur or not a.currency or a.currency == exp_cur]
            if not pool:
                bad.append(f"{label}: -")
            elif not any(a.value == exp_val for a in pool):
                bad.append(f"{label}: {_amounts_summary(pool)}")
        if bad:
            findings.append(Finding(
                "amount", RED, "r_amount_expected_mismatch",
                {"expected": f"{exp_cur} {fmt_money(exp_val)}".strip()},
                " / ".join(bad)))
        else:
            findings.append(Finding(
                "amount", GREEN, "r_amount_expected_ok",
                {"expected": f"{exp_cur} {fmt_money(exp_val)}".strip()}))
        return
    if not body_amounts and all(not a.amounts for a in atts):
        findings.append(Finding("amount", YELLOW, "r_amount_none"))
        return
    if body_amounts and atts and all(not a.amounts for a in atts if a.readable):
        findings.append(Finding("amount", YELLOW, "r_amount_att_none",
                                {}, _amounts_summary(body_amounts)))
        return
    if not body_amounts and atts and any(a.amounts for a in atts):
        findings.append(Finding("amount", YELLOW, "r_amount_body_none",
                                {}, " / ".join(
                                    f"{a.name}: {_amounts_summary(a.amounts)}"
                                    for a in atts if a.amounts)))
        return
    body_totals = _totals_by_currency(body_amounts)
    worst_level = GREEN
    evid = []
    for a in atts:
        if not a.readable:
            continue
        att_totals = _totals_by_currency(a.amounts)
        if body_totals and att_totals:
            shared = set(body_totals) & set(att_totals)
            if not shared:
                evid.append(f"{a.name}: {_amounts_summary(a.amounts)}")
                worst_level = RED
                continue
            for cur in shared:
                if body_totals[cur] != att_totals[cur]:
                    evid.append(
                        f"{inp.labels['body']}: {cur} "
                        f"{', '.join(fmt_money(v) for v in sorted(body_totals[cur]))}"
                        f" / {a.name}: {cur} "
                        f"{', '.join(fmt_money(v) for v in sorted(att_totals[cur]))}")
                    worst_level = RED
        elif body_totals or att_totals:
            pool_body = {a2.value for a2 in body_amounts}
            pool_att = {a2.value for a2 in a.amounts}
            if pool_body & pool_att:
                evid.append(f"{a.name}: {_amounts_summary(a.amounts)}")
            else:
                evid.append(f"{a.name}: {_amounts_summary(a.amounts)}")
                if worst_level != RED:
                    worst_level = YELLOW
        else:
            pool_body = {a2.value for a2 in body_amounts}
            pool_att = {a2.value for a2 in a.amounts}
            if pool_body & pool_att:
                evid.append(f"{a.name}: {_amounts_summary(a.amounts)}")
            else:
                evid.append(f"{a.name}: {_amounts_summary(a.amounts)}")
                if worst_level != RED:
                    worst_level = YELLOW
    if worst_level == RED:
        findings.append(Finding("amount", RED, "r_amount_mismatch", {},
                                " / ".join(evid)))
    elif worst_level == YELLOW:
        findings.append(Finding("amount", YELLOW, "r_amount_unmatched", {},
                                " / ".join(evid)))
    else:
        findings.append(Finding(
            "amount", GREEN, "r_amount_ok",
            {"body": _amounts_summary(body_amounts)},
            " / ".join(evid)))


def _check_dates(inp, body_dates, findings):
    exp_dates = extract_dates(inp.expected_date)
    if exp_dates:
        exp = exp_dates[0].day
        targets = [(inp.labels["body"], body_dates)]
        targets += [(a.name, a.dates) for a in inp.attachments]
        bad = []
        for label, dates in targets:
            if dates and all(d.day != exp for d in dates):
                bad.append(f"{label}: {', '.join(str(d.day) for d in dates)}")
        if bad:
            findings.append(Finding("date", YELLOW, "r_date_expected_mismatch",
                                    {"expected": str(exp)}, " / ".join(bad)))
        else:
            findings.append(Finding("date", GREEN, "r_date_expected_ok",
                                    {"expected": str(exp)}))
        return
    if not body_dates and all(not a.dates for a in inp.attachments):
        findings.append(Finding("date", GREEN, "r_date_none"))
        return
    level = GREEN
    evid = []
    for a in inp.attachments:
        if not a.readable:
            continue
        for kind in ("deadline", "validity", "generic"):
            bset = {d.day for d in body_dates if d.kind == kind}
            aset = {d.day for d in a.dates if d.kind == kind}
            if bset and aset and not (bset & aset):
                evid.append(
                    f"{kind}: {inp.labels['body']} "
                    f"{', '.join(str(d) for d in sorted(bset))} / {a.name} "
                    f"{', '.join(str(d) for d in sorted(aset))}")
                level = worst(level, RED if kind in ("deadline", "validity")
                              else YELLOW)
    if level == RED:
        findings.append(Finding("date", RED, "r_date_deadline_mismatch", {},
                                " / ".join(evid)))
    elif level == YELLOW:
        findings.append(Finding("date", YELLOW, "r_date_mismatch", {},
                                " / ".join(evid)))
    else:
        findings.append(Finding("date", GREEN, "r_date_ok"))


def _check_companies(inp, body_companies, findings):
    exp_norm = normalize_company(inp.expected_company) \
        if inp.expected_company.strip() else ""
    att_companies = {}
    for a in inp.attachments:
        if a.readable:
            att_companies[a.name] = a.companies
    if exp_norm:
        in_body = exp_norm in body_companies
        in_att = any(exp_norm in c for c in att_companies.values())
        if in_body or in_att:
            findings.append(Finding("company", GREEN, "r_company_expected_ok",
                                    {"company": inp.expected_company}))
        else:
            seen = list(body_companies.values()) + \
                [v for c in att_companies.values() for v in c.values()]
            findings.append(Finding(
                "company", YELLOW, "r_company_expected_notfound",
                {"company": inp.expected_company}, ", ".join(seen[:4])))
        return
    if not body_companies and not any(att_companies.values()):
        findings.append(Finding("company", GREEN, "r_company_none"))
        return
    level = GREEN
    evid = []
    for name, companies in att_companies.items():
        if not companies:
            findings.append(Finding("company", YELLOW,
                                    "r_company_att_none", {"file": name}))
            level = worst(level, YELLOW)
            continue
        if not body_companies:
            continue
        if set(body_companies) & set(companies):
            evid.append(f"{name}: {', '.join(companies.values())}")
            continue
        same_script = any(
            _script_of(b) == _script_of(a)
            for b in body_companies for a in companies)
        evid.append(
            f"{inp.labels['body']}: {', '.join(body_companies.values())} / "
            f"{name}: {', '.join(companies.values())}")
        level = worst(level, RED if same_script else YELLOW)
    if any(f.check == "company" for f in findings):
        return
    if level == RED:
        findings.append(Finding("company", RED, "r_company_mismatch", {},
                                " / ".join(evid)))
    elif level == YELLOW:
        findings.append(Finding("company", YELLOW, "r_company_script", {},
                                " / ".join(evid)))
    else:
        findings.append(Finding("company", GREEN, "r_company_ok", {},
                                " / ".join(evid)))


def _script_of(norm):
    if re.search(r"[぀-ヿ㐀-鿿]", norm):
        return "ja"
    if re.search(r"[a-z]", norm):
        return "latin"
    if re.search(r"[가-힯]", norm):
        return "ko"
    if re.search(r"[а-я]", norm):
        return "cyrillic"
    return "other"


def _check_docnums(inp, body_docnums, findings):
    exp_norm = normalize_docnum(inp.expected_docnum) \
        if inp.expected_docnum.strip() else ""
    if exp_norm:
        in_body = exp_norm in body_docnums
        in_att = any(exp_norm in a.doc_numbers for a in inp.attachments)
        if in_body or in_att:
            findings.append(Finding("docnum", GREEN, "r_docnum_expected_ok",
                                    {"docnum": inp.expected_docnum}))
        else:
            findings.append(Finding("docnum", RED, "r_docnum_expected_mismatch",
                                    {"docnum": inp.expected_docnum}))
        return
    if not body_docnums:
        findings.append(Finding("docnum", GREEN, "r_docnum_none"))
        return
    level = GREEN
    evid = []
    for a in inp.attachments:
        if not a.readable or not a.doc_numbers:
            continue
        if set(body_docnums) & set(a.doc_numbers):
            evid.append(f"{a.name}: {', '.join(a.doc_numbers.values())}")
        else:
            evid.append(
                f"{inp.labels['body']}: {', '.join(body_docnums.values())} / "
                f"{a.name}: {', '.join(a.doc_numbers.values())}")
            level = RED
    if level == RED:
        findings.append(Finding("docnum", RED, "r_docnum_mismatch", {},
                                " / ".join(evid)))
    else:
        findings.append(Finding("docnum", GREEN, "r_docnum_ok", {},
                                " / ".join(evid)))


def _check_domain(inp, body_companies, findings):
    emails = parse_emails(inp.recipients_text)
    if not emails:
        findings.append(Finding("domain", RED, "r_no_recipient"))
        return
    domains = sorted({_domain_of(e) for e in emails})
    exp_domain = to_half(inp.expected_domain).strip().lower().lstrip("@")
    if exp_domain:
        bad = [d for d in domains if d != exp_domain]
        if bad:
            findings.append(Finding(
                "domain", RED, "r_domain_expected_mismatch",
                {"expected": exp_domain}, ", ".join(domains)))
        else:
            findings.append(Finding("domain", GREEN, "r_domain_expected_ok",
                                    {"expected": exp_domain}))
        return
    comp_tokens = set()
    sources = list(body_companies.keys())
    if inp.expected_company.strip():
        sources.append(normalize_company(inp.expected_company))
    for a in inp.attachments:
        sources += list(a.companies.keys())
    for s in sources:
        comp_tokens |= company_tokens(s)
    # A domain label that is exactly the full normalized company name
    # (e.g. company "Alphacorp" vs domain alphacorp.co.jp) also counts as
    # an exact match - still exact-after-normalization, never similarity.
    comp_norms = {s for s in sources if s}
    level = GREEN
    evid = []
    for d in domains:
        if d in FREEMAIL_DOMAINS:
            findings.append(Finding("domain", YELLOW, "r_domain_freemail",
                                    {"domain": d}))
            level = worst(level, YELLOW)
            continue
        dtoks = _domain_tokens(d)
        if comp_tokens and ((comp_tokens & dtoks) or (comp_norms & dtoks)):
            evid.append(d)
        elif comp_tokens:
            findings.append(Finding("domain", YELLOW, "r_domain_mismatch",
                                    {"domain": d}))
            level = worst(level, YELLOW)
        else:
            findings.append(Finding("domain", YELLOW,
                                    "r_domain_unverifiable", {"domain": d}))
            level = worst(level, YELLOW)
    if level == GREEN:
        findings.append(Finding("domain", GREEN, "r_domain_ok", {},
                                ", ".join(evid)))


# ---------------------------------------------------------------------------
# filename / version checks
# ---------------------------------------------------------------------------

_FILENAME_DATE_PATTERNS = [
    re.compile(r"(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])"),
    re.compile(r"(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})"),
]
_DRAFT_TOKENS = ("draft", "下書き", "旧", "old", "修正前", "仮版", "temp",
                 "bak", "entwurf", "brouillon", "borrador", "bozza",
                 "rascunho", "черновик", "초안", "草稿")
_VERSION_RE = re.compile(r"(?:^|[_\-\s])v(?:er)?[\s_\-]?(\d+)", re.IGNORECASE)


def extract_filename_dates(name):
    out = []
    for pat in _FILENAME_DATE_PATTERNS:
        for m in pat.finditer(to_half(name)):
            try:
                out.append(datetime.date(int(m.group(1)), int(m.group(2)),
                                         int(m.group(3))))
            except ValueError:
                pass
    return out


def _filename_base_key(name):
    stem = os.path.splitext(to_half(name))[0].lower()
    stem = _FILENAME_DATE_PATTERNS[0].sub("", stem)
    stem = _FILENAME_DATE_PATTERNS[1].sub("", stem)
    stem = _VERSION_RE.sub("", stem)
    for tok in _DRAFT_TOKENS:
        stem = stem.replace(tok, "")
    return re.sub(r"[^a-z0-9぀-ヿ㐀-鿿]+", "", stem)


def suggest_rename(att):
    stem, ext = os.path.splitext(att.name)
    ascii_stem = re.sub(r"[^A-Za-z0-9]+", "_", to_half(stem)).strip("_")
    ascii_stem = re.sub(r"_+", "_", ascii_stem)
    if len(ascii_stem) < 3:
        docnums = list(att.doc_numbers.values())
        if docnums:
            ascii_stem = re.sub(r"[^A-Za-z0-9]+", "-", docnums[0])
        else:
            ascii_stem = "document"
    fdates = extract_filename_dates(att.name)
    if fdates and str(fdates[0].year) not in ascii_stem:
        ascii_stem += "_" + fdates[0].strftime("%Y%m%d")
    return ascii_stem + ext.lower()


def _check_version_and_filename(inp, body_dates, findings, renames):
    all_dates = list(body_dates)
    for a in inp.attachments:
        all_dates += a.dates
    generic_dates = [d.day for d in all_dates if d.kind == "generic"]
    all_days = [d.day for d in all_dates]
    charset = COUNTRY_CHARSETS.get(inp.country, "utf-8")
    version_level = GREEN
    # duplicate / multiple versions of the same document
    base_map = {}
    for a in inp.attachments:
        base_map.setdefault(_filename_base_key(a.name), []).append(a)
    for base, group in base_map.items():
        if len(group) > 1 and base:
            names = ", ".join(g.name for g in group)
            findings.append(Finding("version", RED, "r_version_duplicate",
                                    {}, names))
            version_level = RED
    docnum_map = {}
    for a in inp.attachments:
        for dn in a.doc_numbers:
            docnum_map.setdefault(dn, []).append(a)
    for dn, group in docnum_map.items():
        if len(group) > 1:
            names = ", ".join(g.name for g in group)
            if not any(f.reason_key == "r_version_duplicate"
                       and f.evidence == names for f in findings):
                findings.append(Finding("version", RED, "r_version_duplicate",
                                        {}, names))
                version_level = RED
    for a in inp.attachments:
        stem_low = to_half(a.name).lower()
        fdates = extract_filename_dates(a.name)
        for fd in fdates:
            if all_days and fd < max(all_days):
                gap = (max(all_days) - fd).days
                lvl = RED if gap >= 30 else YELLOW
                findings.append(Finding(
                    "version", lvl, "r_version_filename_old",
                    {"file": a.name, "filedate": str(fd),
                     "newest": str(max(all_days))}))
                version_level = worst(version_level, lvl)
        draft_hit = [t for t in _DRAFT_TOKENS if t in stem_low]
        if draft_hit:
            findings.append(Finding("version", YELLOW, "r_version_draft",
                                    {"file": a.name, "token": draft_hit[0]}))
            version_level = worst(version_level, YELLOW)
        elif _VERSION_RE.search(stem_low):
            findings.append(Finding("version", YELLOW, "r_version_token",
                                    {"file": a.name}))
            version_level = worst(version_level, YELLOW)
        if a.mtime and generic_dates:
            mday = datetime.date.fromtimestamp(a.mtime)
            if (max(generic_dates) - mday).days >= 90:
                findings.append(Finding("version", YELLOW, "r_version_mtime",
                                        {"file": a.name, "mtime": str(mday)}))
                version_level = worst(version_level, YELLOW)
        # ---- filename mojibake / safety ----
        name = a.name
        issues = []
        has_japanese = bool(re.search(r"[぀-ヿ㐀-鿿]", name))
        if has_japanese and inp.country != "JP":
            issues.append(("r_filename_japanese", YELLOW))
        if charset != "utf-8":
            try:
                name.encode(charset)
            except (UnicodeEncodeError, LookupError):
                if not has_japanese:
                    issues.append(("r_filename_unencodable", YELLOW))
        if re.search(r"[\U0001F000-\U0001FAFF☀-➿]", name) or \
                re.search(r"[ｦ-ﾝ]", to_half(name)) or "〜" in name or "～" in name:
            issues.append(("r_filename_emoji", YELLOW))
        if "　" in name or re.search(r'[<>:"/\\|?*]', name) or \
                name.rstrip() != name or \
                os.path.splitext(name)[0].endswith("."):
            issues.append(("r_filename_forbidden", YELLOW))
        if len(name) > 100:
            issues.append(("r_filename_long", YELLOW))
        for key, lvl in issues:
            findings.append(Finding("filename", lvl, key, {"file": name}))
        if issues:
            renames[a.path] = suggest_rename(a)
    if version_level == GREEN:
        findings.append(Finding("version", GREEN, "r_version_ok"))
    if not any(f.check == "filename" for f in findings):
        findings.append(Finding("filename", GREEN, "r_filename_ok"))


def _check_readable(inp, findings):
    for a in inp.attachments:
        if not a.readable:
            findings.append(Finding("readable", YELLOW, "r_unreadable",
                                    {"file": a.name}))
        elif a.via_ocr:
            # Provenance: this attachment's text came from OCR.
            findings.append(Finding("readable", GREEN, "r_read_via_ocr",
                                    {"file": a.name}, "OCR"))
    if not any(f.check == "readable" for f in findings) and inp.attachments:
        findings.append(Finding("readable", GREEN, "r_readable_ok"))


def _check_ocr_caution(inp, findings):
    """Advisory row shown once when any attachment was read through OCR.

    It is deliberately excluded from the overall traffic light (see
    run_checks): matching content stays green, but the user is always
    reminded that OCR can misread and numbers must be compared against
    the original document.
    """
    ocr_files = [a.name for a in inp.attachments if a.via_ocr]
    if ocr_files:
        joined = ", ".join(ocr_files)
        findings.append(Finding("ocr", YELLOW, "r_ocr_caution",
                                {"files": joined}, joined))


# ---------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------

def run_checks(inp):
    findings = []
    renames = {}
    body_amounts = extract_amounts(inp.body + "\n" + inp.subject)
    body_dates = extract_dates(inp.body + "\n" + inp.subject)
    body_companies = extract_companies(inp.body + "\n" + inp.subject)
    body_docnums = extract_doc_numbers(inp.body + "\n" + inp.subject)

    _check_attach(inp, findings)
    _check_amounts(inp, body_amounts, findings)
    _check_dates(inp, body_dates, findings)
    _check_companies(inp, body_companies, findings)
    _check_docnums(inp, body_docnums, findings)
    _check_domain(inp, body_companies, findings)
    _check_version_and_filename(inp, body_dates, findings, renames)
    _check_readable(inp, findings)
    _check_ocr_caution(inp, findings)

    findings.sort(key=lambda f: (CHECK_ORDER.index(f.check)
                                 if f.check in CHECK_ORDER else 99,
                                 -LEVEL_ORDER[f.level]))
    # The OCR caution row is advisory only and never changes the light.
    judged = [f.level for f in findings if f.check != "ocr"]
    overall = worst(*judged) if judged else GREEN
    return Report(overall=overall, findings=findings, rename_suggestions=renames)


def export_renamed_copies(renames, attachments, out_dir):
    """Copy attachments to out_dir under their suggested safe names.
    Only called when the user explicitly presses the button."""
    os.makedirs(out_dir, exist_ok=True)
    by_path = {a.path: a for a in attachments}
    written = []
    for path, new_name in renames.items():
        if path not in by_path:
            continue
        dest = os.path.join(out_dir, new_name)
        base, ext = os.path.splitext(dest)
        n = 2
        while os.path.exists(dest):
            dest = f"{base}_{n}{ext}"
            n += 1
        shutil.copyfile(path, dest)
        written.append(dest)
    return written

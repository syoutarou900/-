# -*- coding: utf-8 -*-
"""UniList core: table IO, column-role inference, deterministic
duplicate-candidate detection, and the human-approved merge engine.

Semi-auto rule (project-wide): the engine only PROPOSES candidate
groups whose normalized keys are exactly equal. Merging happens only
for groups a human explicitly approves, the source file is never
modified, every merge is logged and can be undone, and pairs a human
marks as 'not duplicates' are remembered.
"""
import csv
import io
import json
import os
import re
from datetime import date, datetime

import normalize as nz

ROLES = ["name", "address", "phone", "email", "id", "other"]
KEY_ROLES = ["name", "phone", "email", "id", "address"]


# ---------------------------------------------------------------------------
# Table IO
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
    for enc in ("utf-8", "shift_jis", "cp1252"):
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
                         (c.isoformat() if isinstance(c, (date, datetime))
                          else str(c)) for c in row])
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


def save_table_csv(table, path, delimiter=","):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=delimiter, lineterminator="\r\n")
        writer.writerow(table.headers)
        writer.writerows(table.rows)


def save_table_xlsx(table, path):
    from openpyxl import Workbook  # lazy
    wb = Workbook()
    ws = wb.active
    ws.append(table.headers)
    for r in table.rows:
        ws.append(r)
    wb.save(path)


# ---------------------------------------------------------------------------
# Column roles: inference + robust resolution of human-typed text
# ---------------------------------------------------------------------------

def _role_key(text):
    """Normalization for role words: width/case folded, spaces and
    punctuation removed - so fullwidth, spaces, case and punctuation
    variants of the same word resolve identically."""
    t = nz.base_normalize(text)
    t = nz.fold_latin_accents(t)
    return re.sub(r"[\s\W_]+", "", t, flags=re.UNICODE)


_ROLE_SYNONYMS = {
    "name": [
        "名前", "氏名", "名称", "会社名", "顧客名", "取引先名", "店名", "担当者名",
        "name", "fullname", "company", "companyname", "customer", "customername",
        "client", "account", "nombre", "empresa", "cliente",
        "nom", "société", "societe", "clientnom",
        "firmenname", "kundenname", "firma", "kunde",
        "nome", "azienda", "cliente", "razãosocial", "razaosocial",
        "название", "компания", "клиент", "наименование",
        "isim", "şirket", "sirket", "müşteri", "musteri", "firmaadi",
        "الاسم", "الشركة", "العميل",
        "nama", "perusahaan", "pelanggan",
        "이름", "회사명", "고객명", "상호", "거래처명",
        "名称", "公司名", "客户名", "客戶名", "公司名稱",
    ],
    "address": [
        "住所", "所在地", "アドレス", "address", "dirección", "direccion",
        "endereço", "endereco", "adresse", "indirizzo", "адрес", "adres",
        "العنوان", "عنوان", "alamat", "주소", "地址", "住址",
    ],
    "phone": [
        "電話", "電話番号", "携帯", "携帯番号", "tel", "telephone", "phone",
        "teléfono", "telefono", "telefone", "telefon", "téléphone",
        "телефон", "هاتف", "الهاتف", "전화", "전화번호", "휴대폰",
        "电话", "電話號碼", "fax", "ファックス",
    ],
    "email": [
        "メール", "メールアドレス", "email", "e-mail", "mail", "correo",
        "courriel", "e-mailadresse", "emailadresse", "posta", "eposta",
        "электроннаяпочта", "почта", "البريد", "بريد", "이메일", "邮箱",
        "郵件", "电子邮箱", "電子郵件",
    ],
    "id": [
        "id", "番号", "顧客番号", "取引先コード", "コード", "法人番号",
        "税番号", "code", "customerid", "clientid", "kundennummer",
        "número", "numero", "código", "codigo", "codice", "numéro",
        "номер", "код", "numara", "kod", "الرقم", "رقم", "nomor",
        "번호", "고객번호", "사업자번호", "編號", "编号", "统一社会信用代码",
        "vat", "taxid", "cif", "cnpj", "cpf", "rfc",
    ],
}
_ROLE_LOOKUP = {}
for _role, _words in _ROLE_SYNONYMS.items():
    for _w in _words:
        _ROLE_LOOKUP[_role_key(_w)] = _role
# the canonical role names themselves also resolve
for _r in ROLES:
    _ROLE_LOOKUP[_role_key(_r)] = _r


def resolve_role(text):
    """Resolve a human-typed role word to a canonical role, tolerating
    fullwidth/halfwidth, case, spaces, punctuation and synonyms.
    Returns None when it cannot be resolved."""
    if text is None:
        return None
    key = _role_key(str(text))
    if not key:
        return None
    return _ROLE_LOOKUP.get(key)


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[\d\s\-()]{7,}$")


def infer_roles(headers, rows):
    """Propose a role per column: header synonyms first, then value
    patterns. Only the first 'name' column is kept as name (further
    name-like columns stay usable but marked 'other' unless a human
    promotes them)."""
    roles = []
    used_name = False
    sample = rows[:200]
    for ci, h in enumerate(headers):
        role = resolve_role(h)
        if role is None:
            values = [r[ci] for r in sample if r[ci].strip()]
            if values:
                email_like = sum(1 for v in values if _EMAIL_RE.match(v.strip()))
                phone_like = sum(1 for v in values
                                 if _PHONE_RE.match(v.strip())
                                 and len(re.sub(r"\D", "", v)) >= 7)
                if email_like >= max(1, len(values) // 2):
                    role = "email"
                elif phone_like >= max(1, len(values) // 2):
                    role = "phone"
            if role is None:
                role = "other"
        if role == "name":
            if used_name:
                role = "other"
            else:
                used_name = True
        roles.append(role)
    return roles


# ---------------------------------------------------------------------------
# Candidate detection (exact-after-normalization only)
# ---------------------------------------------------------------------------

class Group:
    """One candidate duplicate group."""
    __slots__ = ("row_indices", "tier", "reasons", "name_key")

    def __init__(self, row_indices, tier, reasons, name_key=""):
        self.row_indices = row_indices      # indices into engine.rows
        self.tier = tier                    # "A" | "B" | "C"
        self.reasons = reasons              # list of roles that matched
        self.name_key = name_key

    def __repr__(self):
        return f"<Group tier={self.tier} rows={self.row_indices} {self.reasons}>"


class _UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _field_keys(role, value):
    """All exact-match keys a cell contributes for its role."""
    if role == "name":
        k = nz.normalize_name(value)
        return {k} if k else set()
    if role == "phone":
        return nz.phone_keys(value)
    if role == "email":
        k = nz.normalize_email(value)
        return {k} if k and "@" in k else set()
    if role == "id":
        k = nz.normalize_id(value)
        return {k} if k else set()
    if role == "address":
        k = nz.normalize_address(value)
        return {k} if k else set()
    return set()


class Engine:
    """Working dataset + candidate detection + approved merges + undo
    + learned not-a-duplicate pairs + session save/load."""

    def __init__(self):
        self.headers = []
        self.roles = []
        self.rows = []              # list of {"uid": int, "values": [str]}
        self._next_uid = 1
        self.source_path = ""
        self.merge_log = []         # list of dicts (see apply_merge)
        self.not_dup = set()        # set of frozenset({sigA, sigB})
        self._original = []         # snapshot at load: [{"uid","values"}]

    # -- loading -------------------------------------------------------------
    def load(self, table, source_path=""):
        self.headers = list(table.headers)
        self.rows = []
        self._next_uid = 1
        for r in table.rows:
            self.rows.append({"uid": self._next_uid,
                              "values": list(r)})
            self._next_uid += 1
        self._original = [{"uid": r["uid"], "values": list(r["values"])}
                          for r in self.rows]
        self.roles = infer_roles(self.headers, table.rows)
        self.source_path = source_path
        self.merge_log = []
        return self

    def set_roles(self, roles):
        assert len(roles) == len(self.headers)
        self.roles = list(roles)

    def _role_cols(self, role):
        return [i for i, r in enumerate(self.roles) if r == role]

    # -- detection ------------------------------------------------------------
    # Roles whose exact key can CREATE a candidate group. Address is a
    # supporting reason only: a shared (possibly partial) address must
    # never glue unrelated rows into a group on its own.
    UNION_ROLES = ("name", "phone", "email", "id")

    def detect(self):
        """Return candidate Groups. Deterministic, dict-based
        (no O(n^2) pairwise scan)."""
        n = len(self.rows)
        uf = _UnionFind(n)
        # per-row exact keys for every key role (computed once)
        row_keys = []
        for row in self.rows:
            per_role = {}
            for role in KEY_ROLES:
                keys = set()
                for ci in self._role_cols(role):
                    keys |= _field_keys(role, row["values"][ci])
                per_role[role] = keys
            row_keys.append(per_role)
        # union rows that share an exact key in a union role
        for role in self.UNION_ROLES:
            m = {}
            for idx in range(n):
                for k in row_keys[idx][role]:
                    m.setdefault(k, []).append(idx)
            for idxs in m.values():
                if len(idxs) >= 2:
                    first = idxs[0]
                    for other in idxs[1:]:
                        uf.union(first, other)
        comps = {}
        for i in range(n):
            comps.setdefault(uf.find(i), []).append(i)
        name_cols = self._role_cols("name")
        groups = []
        for members in comps.values():
            if len(members) < 2:
                continue
            members = sorted(members)
            # reasons: roles where >=2 members share one exact key
            reasons = []
            for role in KEY_ROLES:
                seen = {}
                for idx in members:
                    for k in row_keys[idx][role]:
                        seen[k] = seen.get(k, 0) + 1
                if any(c >= 2 for c in seen.values()):
                    reasons.append(role)
            # name agreement: all members share one non-empty name key
            name_key = ""
            name_same = False
            if name_cols:
                keys = {nz.normalize_name(self.rows[idx]["values"][name_cols[0]])
                        for idx in members}
                if len(keys) == 1 and next(iter(keys)):
                    name_same = True
                    name_key = next(iter(keys))
            if name_same and any(r in reasons
                                 for r in ("phone", "email", "address")):
                tier = "A"
            elif name_same:
                tier = "B"
            elif any(r in reasons for r in ("phone", "email", "id")):
                tier = "C"
            else:
                continue
            # learned exclusions (pairs only)
            if len(members) == 2:
                sigs = frozenset(
                    nz.row_signature(self.rows[i]["values"]) for i in members)
                if len(sigs) == 2 and sigs in self.not_dup:
                    continue
            groups.append(Group(members, tier, reasons, name_key))
        tier_order = {"A": 0, "B": 1, "C": 2}
        groups.sort(key=lambda g: (tier_order[g.tier], -len(g.row_indices),
                                   g.row_indices[0]))
        return groups

    # -- merging ---------------------------------------------------------------
    def default_choices(self, group):
        """Per column: first non-empty value among members (row order)."""
        choices = {}
        for ci in range(len(self.headers)):
            val = ""
            for idx in group.row_indices:
                v = self.rows[idx]["values"][ci]
                if v.strip():
                    val = v
                    break
            choices[ci] = val
        return choices

    def apply_merge(self, group, choices, when=None):
        """Merge one human-approved group. Returns the log entry."""
        members = [self.rows[i] for i in group.row_indices]
        positions = list(group.row_indices)
        merged_values = [choices.get(ci, "") for ci in range(len(self.headers))]
        merged_uid = self._next_uid
        self._next_uid += 1
        entry = {
            "when": when or datetime.now().isoformat(timespec="seconds"),
            "tier": group.tier,
            "reasons": list(group.reasons),
            "members": [{"uid": m["uid"], "values": list(m["values"]),
                         "position": p}
                        for m, p in zip(members, positions)],
            "merged_uid": merged_uid,
            "merged_values": list(merged_values),
        }
        member_uids = {m["uid"] for m in members}
        first_pos = min(positions)
        new_rows = []
        for i, row in enumerate(self.rows):
            if i == first_pos:
                new_rows.append({"uid": merged_uid, "values": list(merged_values)})
            if row["uid"] in member_uids:
                continue
            new_rows.append(row)
        self.rows = new_rows
        self.merge_log.append(entry)
        return entry

    def undo_last_merge(self):
        """Undo the most recent merge, restoring the original rows at
        their original positions. Returns the undone entry or None."""
        if not self.merge_log:
            return None
        entry = self.merge_log.pop()
        merged_uid = entry["merged_uid"]
        self.rows = [r for r in self.rows if r["uid"] != merged_uid]
        for m in sorted(entry["members"], key=lambda x: x["position"]):
            pos = min(m["position"], len(self.rows))
            self.rows.insert(pos, {"uid": m["uid"],
                                   "values": list(m["values"])})
        return entry

    # -- learned not-a-duplicate ----------------------------------------------
    def mark_not_duplicate(self, group):
        """Record all pairs in the group as 'not duplicates' (learned).
        Returns the number of pairs recorded."""
        sigs = [nz.row_signature(self.rows[i]["values"])
                for i in group.row_indices]
        count = 0
        for a in range(len(sigs)):
            for b in range(a + 1, len(sigs)):
                if sigs[a] != sigs[b]:
                    self.not_dup.add(frozenset((sigs[a], sigs[b])))
                    count += 1
        return count

    # -- export ------------------------------------------------------------------
    def export_table(self):
        return Table(list(self.headers),
                     [list(r["values"]) for r in self.rows])

    def log_records(self):
        """Merge log as flat rows for CSV export."""
        out = []
        for e in self.merge_log:
            names = []
            name_cols = self._role_cols("name")
            for m in e["members"]:
                names.append(m["values"][name_cols[0]] if name_cols else "")
            chosen = "; ".join(
                f"{self.headers[ci]}={v}"
                for ci, v in enumerate(e["merged_values"]) if v)
            out.append({
                "when": e["when"], "tier": e["tier"],
                "reasons": "+".join(e["reasons"]),
                "members": " | ".join(names),
                "member_count": len(e["members"]),
                "chosen": chosen,
            })
        return out

    # -- session -------------------------------------------------------------------
    def save_session(self, path):
        data = {
            "version": 1,
            "headers": self.headers,
            "roles": self.roles,
            "source_path": self.source_path,
            "next_uid": self._next_uid,
            "original": self._original,
            "rows": [{"uid": r["uid"], "values": r["values"]}
                     for r in self.rows],
            "merge_log": self.merge_log,
            "not_dup": [sorted(p) for p in self.not_dup],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)

    def load_session(self, path):
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.headers = data["headers"]
        self.roles = data["roles"]
        self.source_path = data.get("source_path", "")
        self._next_uid = data["next_uid"]
        self._original = data["original"]
        self.rows = [{"uid": r["uid"], "values": list(r["values"])}
                     for r in data["rows"]]
        self.merge_log = data["merge_log"]
        self.not_dup = {frozenset(p) for p in data.get("not_dup", [])}
        return self

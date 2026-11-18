# -*- coding: utf-8 -*-
"""Read-only analysis engine for VersionDetective.

Everything in this module only READS files.  Nothing here writes to,
moves or deletes a user file.

Pipeline
--------
1. ``extract(path)`` -> FileInfo (content lines / cells, hashes,
   internal modified datetime, or an error reason that is shown to
   the user, never silently dropped).
2. ``build_groups()`` -> stage 1: identical-content groups
   (deterministic), stage 2: version *candidate* groups (name-stem +
   content similarity evidence; never auto-confirmed).
3. ``rank_latest()`` -> latest candidate with reasons, including
   branch detection (two versions each holding content the other
   lacks -> no verdict).
4. ``diff_infos()`` -> line-level (text) or cell-level (xlsx/csv)
   diff with counts and examples.
"""

from __future__ import annotations

import csv
import difflib
import hashlib
import io
import os
import re
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

MAX_FULL_PARSE_BYTES = 100 * 1024 * 1024  # >100MB: hash only
WARN_FILE_COUNT = 2000

TEXT_EXTS = {".txt", ".md"}
OFFICE_TEXT_EXTS = {".docx", ".pptx"}
CELL_EXTS = {".xlsx"}
CSV_EXTS = {".csv"}
PDF_EXTS = {".pdf"}
SUPPORTED_EXTS = TEXT_EXTS | OFFICE_TEXT_EXTS | CELL_EXTS | CSV_EXTS | PDF_EXTS


# ----------------------------------------------------------------------
# Data model
# ----------------------------------------------------------------------

@dataclass
class FileInfo:
    path: str
    name: str
    ext: str
    size: int = 0
    mtime: float = 0.0
    status: str = "ok"           # ok | hash_only | error
    error_reason: str = ""       # i18n key suffix, e.g. "encrypted"
    kind: str = "none"           # text | cells | none
    lines: list = field(default_factory=list)   # text content
    cells: dict = field(default_factory=dict)   # (sheet, coord) -> value
    content_hash: str = ""       # hash of extracted content (or bytes)
    file_hash: str = ""          # sha256 of raw bytes
    internal_modified: datetime | None = None
    internal_source: str = ""    # "office" | "pdf" | ""

    @property
    def effective_dt(self) -> datetime:
        """Internal content datetime wins over the file mtime."""
        if self.internal_modified is not None:
            return self.internal_modified
        return datetime.fromtimestamp(self.mtime, tz=timezone.utc)

    @property
    def dt_source(self) -> str:
        if self.internal_modified is not None:
            return self.internal_source  # office / pdf
        return "mtime"

    def sim_items(self) -> set:
        """Item set used for similarity / diff-direction judgements."""
        if self.kind == "cells":
            return {f"{s}!{c}={v}" for (s, c), v in self.cells.items()}
        if self.kind == "text":
            return set(self.lines)
        return set()

    def content_keys(self) -> set:
        """Identity keys of the content pieces, WITHOUT values.

        Used for branch detection: a spreadsheet cell whose value
        was edited keeps its coordinate key, so an ordinary edit is
        not mistaken for a divergence.  A branch needs content keys
        that are entirely absent from the other side, both ways.
        """
        if self.kind == "cells":
            return set(self.cells.keys())
        if self.kind == "text":
            return set(self.lines)
        return set()

    def stem_key(self) -> str:
        return stem_key(self.name)


# ----------------------------------------------------------------------
# Name stems (version words removed)
# ----------------------------------------------------------------------

_VERSION_PATTERNS = [
    r"本当の最終版", r"最終版", r"最終", r"提出用", r"提出", r"修正版", r"修正",
    r"改訂版", r"改訂", r"更新版", r"更新", r"新版", r"旧版", r"コピー",
    r"ドラフト", r"下書き", r"完成版", r"確定版", r"正式版",
    r"final", r"draft", r"copy", r"rev(?:ision)?", r"ver(?:sion)?",
    r"v(?=\d)", r"r(?=\d)",
]
_VERSION_RE = re.compile(
    r"(?:" + "|".join(_VERSION_PATTERNS) + r")\s*\d*(?:\.\d+)*",
    re.IGNORECASE)
_DATE_RE = re.compile(
    r"(?:20\d{2}[-_/年]?\s?\d{1,2}[-_/月]?\s?\d{1,2}日?"
    r"|20\d{6,8}|\d{1,2}[-_/]\d{1,2})")
_NUM_SUFFIX_RE = re.compile(r"(?:\(\d+\)|（\d+）|[\s_\-]\d{1,3})$")
_SEP_RE = re.compile(r"[\s_\-・．.、,，()（）\[\]]+")


def stem_key(name: str) -> str:
    """Normalised document stem: file name minus extension, version
    words, dates and copy numbers.  Two files of the same document in
    different versions should land on the same stem key."""
    stem = os.path.splitext(name)[0].lower()
    prev = None
    while prev != stem:
        prev = stem
        stem = _VERSION_RE.sub(" ", stem)
        stem = _DATE_RE.sub(" ", stem)
        stem = _NUM_SUFFIX_RE.sub("", stem.strip())
    return _SEP_RE.sub("", stem)


def stem_tokens(name: str) -> set:
    stem = os.path.splitext(name)[0].lower()
    stem = _VERSION_RE.sub(" ", stem)
    stem = _DATE_RE.sub(" ", stem)
    return {t for t in _SEP_RE.split(stem) if t}


def stem_similarity(a: str, b: str) -> float:
    ka, kb = stem_key(a), stem_key(b)
    if ka and ka == kb:
        return 1.0
    ta, tb = stem_tokens(a), stem_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# ----------------------------------------------------------------------
# Content extraction (read-only, stdlib only)
# ----------------------------------------------------------------------

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _content_hash(lines=None, cells=None) -> str:
    h = hashlib.sha256()
    if cells:
        for key in sorted(cells):
            h.update(f"{key[0]}!{key[1]}={cells[key]}\n".encode("utf-8"))
    else:
        for line in lines or []:
            h.update((line + "\n").encode("utf-8"))
    return h.hexdigest()


def _norm_line(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _parse_core_xml(zf: zipfile.ZipFile):
    """docProps/core.xml -> dcterms:modified as aware datetime."""
    try:
        data = zf.read("docProps/core.xml")
    except KeyError:
        return None
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    for el in root.iter():
        if el.tag.endswith("}modified") or el.tag == "modified":
            txt = (el.text or "").strip()
            if txt:
                try:
                    dt = datetime.fromisoformat(txt.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except ValueError:
                    return None
    return None


_NS_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_NS_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_NS_SS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_NS_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _extract_docx(zf: zipfile.ZipFile) -> list:
    root = ET.fromstring(zf.read("word/document.xml"))
    lines = []
    for para in root.iter(_NS_W + "p"):
        text = "".join(t.text or "" for t in para.iter(_NS_W + "t"))
        text = _norm_line(text)
        if text:
            lines.append(text)
    return lines


def _extract_pptx(zf: zipfile.ZipFile) -> list:
    lines = []
    names = sorted(n for n in zf.namelist()
                   if re.match(r"ppt/slides/slide\d+\.xml$", n))
    for name in names:
        root = ET.fromstring(zf.read(name))
        slide_no = int(re.search(r"(\d+)\.xml$", name).group(1))
        for para in root.iter(_NS_A + "p"):
            text = "".join(t.text or "" for t in para.iter(_NS_A + "t"))
            text = _norm_line(text)
            if text:
                lines.append(f"[slide {slide_no}] {text}")
    return lines


def _col_name(idx: int) -> str:
    name = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        name = chr(65 + rem) + name
    return name


def _extract_xlsx(zf: zipfile.ZipFile) -> dict:
    shared = []
    if "xl/sharedStrings.xml" in zf.namelist():
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in root.iter(_NS_SS + "si"):
            shared.append("".join(t.text or ""
                                  for t in si.iter(_NS_SS + "t")))
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = {}
    if "xl/_rels/workbook.xml.rels" in zf.namelist():
        rroot = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        for rel in rroot.iter(_NS_REL + "Relationship"):
            rels[rel.get("Id")] = rel.get("Target")
    cells = {}
    sheets_el = wb.find(_NS_SS + "sheets")
    if sheets_el is None:
        return cells
    for pos, sheet in enumerate(sheets_el.iter(_NS_SS + "sheet")):
        sname = sheet.get("name") or f"Sheet{pos + 1}"
        target = rels.get(sheet.get(_NS_R + "id"), "")
        path = "xl/" + target.lstrip("/")
        if path not in zf.namelist():
            path = f"xl/worksheets/sheet{pos + 1}.xml"
        if path not in zf.namelist():
            continue
        root = ET.fromstring(zf.read(path))
        for c in root.iter(_NS_SS + "c"):
            coord = c.get("r") or ""
            ctype = c.get("t")
            value = ""
            if ctype == "inlineStr":
                is_el = c.find(_NS_SS + "is")
                if is_el is not None:
                    value = "".join(t.text or ""
                                    for t in is_el.iter(_NS_SS + "t"))
            else:
                v = c.find(_NS_SS + "v")
                if v is not None and v.text is not None:
                    if ctype == "s":
                        try:
                            value = shared[int(v.text)]
                        except (ValueError, IndexError):
                            value = v.text
                    else:
                        value = v.text
            value = _norm_line(str(value))
            if value:
                cells[(sname, coord)] = value
    return cells


def _decode_text_bytes(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "shift_jis", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode("utf-8", errors="replace")


def _extract_csv(data: bytes) -> dict:
    text = _decode_text_bytes(data)
    cells = {}
    reader = csv.reader(io.StringIO(text))
    for r, row in enumerate(reader):
        for cidx, value in enumerate(row):
            value = _norm_line(value)
            if value:
                cells[("CSV", f"{_col_name(cidx)}{r + 1}")] = value
    return cells


_PDF_MODDATE_RE = re.compile(rb"/ModDate\s*\(\s*D:([0-9]{4,14})")
_PDF_ENCRYPT_RE = re.compile(rb"/Encrypt\b")


def _pdf_moddate(data: bytes):
    m = _PDF_MODDATE_RE.search(data)
    if not m:
        return None
    digits = m.group(1).decode("ascii", errors="ignore")
    try:
        dt = datetime.strptime(digits[:14].ljust(14, "0"), "%Y%m%d%H%M%S")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _pdf_stream_text(data: bytes) -> list:
    """Best-effort text from uncompressed/FlateDecode content streams.

    Handles literal (...) and hex <...> strings in Tj / TJ / '
    operators with WinAnsi-ish bytes and UTF-16BE hex strings.
    Anything more exotic degrades to 'no text found' (the caller
    then reports the PDF as hash-only), never to a crash.
    """
    lines = []
    for m in re.finditer(rb"stream\r?\n", data):
        start = m.end()
        end = data.find(b"endstream", start)
        if end < 0:
            continue
        raw = data[start:end]
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            pass  # uncompressed stream: use as-is
        cur = []

        def flush():
            if cur:
                lines.append("".join(cur))
                cur.clear()

        token_re = re.compile(
            rb"\((?:\\.|[^\\()])*\)|<([0-9A-Fa-f\s]+)>"
            rb"|\b(Tj|TJ|'|Td|TD|Tm|T\*)\b", re.DOTALL)
        pos = 0
        pending = []  # string pieces waiting for a show operator
        for tm in token_re.finditer(raw):
            tok = tm.group(0)
            op = tm.group(2)
            if op is not None:
                if op in (b"Tj", b"TJ", b"'"):
                    cur.extend(pending)
                    pending = []
                    if op == b"'":
                        flush()
                elif op in (b"Td", b"TD", b"Tm", b"T*"):
                    pending = []
                    flush()
                continue
            if tok.startswith(b"("):
                body = tok[1:-1]
                body = re.sub(rb"\\([()\\])", rb"\1", body)
                body = body.replace(rb"\\n", b" ").replace(rb"\\r", b" ")
                pending.append(body.decode("latin-1", errors="replace"))
            else:
                hexs = re.sub(rb"\s+", b"", tm.group(1) or b"")
                try:
                    bts = bytes.fromhex(hexs.decode("ascii"))
                except ValueError:
                    continue
                if bts.startswith(b"\xfe\xff"):
                    pending.append(bts[2:].decode("utf-16-be",
                                                  errors="replace"))
                else:
                    pending.append(bts.decode("latin-1", errors="replace"))
            pos = tm.end()
        flush()
    out = []
    for line in lines:
        line = _norm_line(line)
        if line:
            out.append(line)
    return out


def extract(path: str) -> FileInfo:
    """Parse one file read-only.  Never raises: failures come back as
    status='error' with a reason key so the UI can list the file."""
    info = FileInfo(path=path, name=os.path.basename(path),
                    ext=os.path.splitext(path)[1].lower())
    try:
        st = os.stat(path)
        info.size = st.st_size
        info.mtime = st.st_mtime
    except OSError:
        info.status = "error"
        info.error_reason = "unreadable"
        return info

    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        info.status = "error"
        info.error_reason = "unreadable"
        return info
    info.file_hash = _sha256_bytes(data)

    if info.size > MAX_FULL_PARSE_BYTES:
        info.status = "hash_only"
        info.error_reason = "too_large"
        info.content_hash = info.file_hash
        return info

    ext = info.ext
    try:
        if ext in (".docx", ".xlsx", ".pptx"):
            if not zipfile.is_zipfile(io.BytesIO(data)):
                info.status = "error"
                info.error_reason = "corrupt"
                return info
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                if zf.testzip() is not None:
                    info.status = "error"
                    info.error_reason = "corrupt"
                    return info
                info.internal_modified = _parse_core_xml(zf)
                if info.internal_modified is not None:
                    info.internal_source = "office"
                if ext == ".docx":
                    info.lines = _extract_docx(zf)
                    info.kind = "text"
                elif ext == ".pptx":
                    info.lines = _extract_pptx(zf)
                    info.kind = "text"
                else:
                    info.cells = _extract_xlsx(zf)
                    info.kind = "cells"
        elif ext in TEXT_EXTS:
            text = _decode_text_bytes(data)
            info.lines = [ln for ln in
                          (_norm_line(x) for x in text.splitlines()) if ln]
            info.kind = "text"
        elif ext in CSV_EXTS:
            info.cells = _extract_csv(data)
            info.kind = "cells"
        elif ext in PDF_EXTS:
            if _PDF_ENCRYPT_RE.search(data):
                info.status = "error"
                info.error_reason = "encrypted"
                info.content_hash = info.file_hash
                return info
            info.internal_modified = _pdf_moddate(data)
            if info.internal_modified is not None:
                info.internal_source = "pdf"
            info.lines = _pdf_stream_text(data)
            if info.lines:
                info.kind = "text"
            else:
                info.status = "hash_only"
                info.error_reason = "pdf_no_text"
        else:
            info.status = "hash_only"
            info.error_reason = "unsupported"
    except (zipfile.BadZipFile, ET.ParseError, KeyError, zlib.error):
        info.status = "error"
        info.error_reason = "corrupt"
        info.content_hash = info.file_hash
        return info
    except Exception:
        info.status = "error"
        info.error_reason = "unreadable"
        info.content_hash = info.file_hash
        return info

    if info.kind == "cells":
        info.content_hash = _content_hash(cells=info.cells)
    elif info.kind == "text":
        info.content_hash = _content_hash(lines=info.lines)
    else:
        info.content_hash = info.file_hash
    if info.status == "ok" and info.kind == "none":
        info.status = "hash_only"
    return info


def scan_folder(root: str, recursive: bool):
    """Yield file paths under root (read-only walk)."""
    if recursive:
        for dirpath, _dirs, files in os.walk(root):
            for f in sorted(files):
                yield os.path.join(dirpath, f)
    else:
        for f in sorted(os.listdir(root)):
            p = os.path.join(root, f)
            if os.path.isfile(p):
                yield p


# ----------------------------------------------------------------------
# Grouping
# ----------------------------------------------------------------------

@dataclass
class Group:
    gid: int
    kind: str                    # exact | candidate
    members: list                # list[FileInfo]
    similarity: float = 0.0      # min pairwise content similarity
    stem: str = ""
    manual_latest: str = ""      # path chosen by the user as latest

    def title(self) -> str:
        return self.stem or (self.members[0].stem_key()
                             if self.members else "")


def content_similarity(a: FileInfo, b: FileInfo) -> float:
    if a.kind == "cells" and b.kind == "cells":
        # Coordinate-aware: a cell present on both sides counts even
        # when its value was edited (half credit), so a spreadsheet
        # revision is not scored as a near-unrelated document.
        ka, kb = set(a.cells), set(b.cells)
        if not ka or not kb:
            return 0.0
        both = ka & kb
        same = sum(1 for k in both if a.cells[k] == b.cells[k])
        return (same + 0.5 * (len(both) - same)) / len(ka | kb)
    ia, ib = a.sim_items(), b.sim_items()
    if not ia or not ib:
        return 0.0
    return len(ia & ib) / len(ia | ib)


STAGE2_MIN_STEM = 0.6
STAGE2_MIN_CONTENT = 0.45


def build_groups(infos, rejected_pairs=None, forced_merges=None):
    """Two-stage grouping.

    Stage 1 (exact): identical content_hash -> same component, a
    deterministic fact.
    Stage 2 (candidate): an edge is added only when BOTH the name
    stem evidence (stem similarity >= 0.6) AND the content
    similarity (>= 0.45) support it.  Components containing any
    stage-2 edge are 'candidate' groups: proposals with visible
    evidence, never verdicts.

    rejected_pairs: set of frozenset({pathA, pathB}) the user split.
    forced_merges: set of frozenset({pathA, pathB}) the user merged.
    Returns (groups, singles).
    """
    rejected_pairs = rejected_pairs or set()
    forced_merges = forced_merges or set()
    usable = [i for i in infos if i.status in ("ok", "hash_only")
              and i.content_hash]
    parent = {i.path: i.path for i in usable}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    stage2_edges = set()
    by_hash = {}
    for info in usable:
        by_hash.setdefault(info.content_hash, []).append(info)
    for same in by_hash.values():
        for other in same[1:]:
            union(same[0].path, other.path)

    n = len(usable)
    for x in range(n):
        for y in range(x + 1, n):
            a, b = usable[x], usable[y]
            pair = frozenset((a.path, b.path))
            if pair in rejected_pairs:
                continue
            if find(a.path) == find(b.path):
                continue
            if a.kind == "none" or b.kind == "none":
                continue  # no content evidence for unsupported formats
            if stem_similarity(a.name, b.name) < STAGE2_MIN_STEM:
                continue
            if content_similarity(a, b) < STAGE2_MIN_CONTENT:
                continue
            union(a.path, b.path)
            stage2_edges.add(pair)

    for pair in forced_merges:
        pa, pb = tuple(pair)
        if pa in parent and pb in parent:
            union(pa, pb)
            stage2_edges.add(pair)

    comps = {}
    for info in usable:
        comps.setdefault(find(info.path), []).append(info)

    groups, singles = [], []
    gid = 0
    for members in comps.values():
        if len(members) == 1:
            singles.append(members[0])
            continue
        gid += 1
        member_paths = {m.path for m in members}
        edge_roots = set()
        for pair in stage2_edges:
            if len(pair & member_paths) == 2:
                edge_roots.add(find(next(iter(pair))))
        has_stage2 = find(members[0].path) in edge_roots
        sims = []
        if has_stage2:
            for x in range(len(members)):
                for y in range(x + 1, len(members)):
                    s = content_similarity(members[x], members[y])
                    if s > 0:
                        sims.append(s)
        groups.append(Group(
            gid=gid,
            kind="candidate" if has_stage2 else "exact",
            members=sorted(members, key=lambda m: m.effective_dt),
            similarity=min(sims) if sims else 0.0,
            stem=members[0].stem_key()))
    groups.sort(key=lambda g: (g.kind != "exact", g.title()))
    return groups, singles


# ----------------------------------------------------------------------
# Latest-candidate ranking + branch detection
# ----------------------------------------------------------------------

@dataclass
class LatestVerdict:
    candidate: FileInfo | None
    reasons: list                # list of (i18n key, params dict)
    branch: bool = False
    branch_with: FileInfo | None = None


def rank_latest(group: Group) -> LatestVerdict:
    members = group.members
    if not members:
        return LatestVerdict(None, [])
    if group.manual_latest:
        for m in members:
            if m.path == group.manual_latest:
                return LatestVerdict(m, [("reason_manual", {})])
    if len(members) == 1:
        return LatestVerdict(members[0], [("reason_only", {})])

    cand = max(members, key=lambda m: m.effective_dt)
    reasons = []
    src_key = {"office": "reason_dt_office", "pdf": "reason_dt_pdf",
               "mtime": "reason_dt_mtime"}[cand.dt_source]
    reasons.append((src_key, {"dt": _fmt_dt(cand.effective_dt)}))

    cand_items = cand.sim_items()
    cand_keys = cand.content_keys()
    branch_with = None
    if cand_keys:
        for other in members:
            if other is cand:
                continue
            other_keys = other.content_keys()
            if not other_keys:
                continue
            if (other_keys - cand_keys) and (cand_keys - other_keys):
                branch_with = other
                break
    if branch_with is not None:
        reasons.append(("reason_branch", {"other": branch_with.name}))
        return LatestVerdict(None, reasons, branch=True,
                             branch_with=branch_with)

    if cand_items:
        others_union = set()
        for m in members:
            if m is not cand:
                others_union |= m.sim_items()
        added = cand_items - others_union
        if added:
            reasons.append(("reason_unique_content", {"n": len(added)}))
        oldest = min(members, key=lambda m: m.effective_dt)
        if oldest is not cand:
            mag = len(cand_items ^ oldest.sim_items())
            if mag:
                reasons.append(("reason_magnitude",
                                {"n": mag, "other": oldest.name}))
    return LatestVerdict(cand, reasons)


def _fmt_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")


# ----------------------------------------------------------------------
# Diff
# ----------------------------------------------------------------------

@dataclass
class DiffResult:
    kind: str                    # text | cells | none
    added: int = 0
    deleted: int = 0
    changed_cells: list = field(default_factory=list)
    added_cells: int = 0
    removed_cells: int = 0
    lines: list = field(default_factory=list)  # (mark, text)


def diff_infos(a: FileInfo, b: FileInfo, max_lines: int = 400) -> DiffResult:
    """Diff from a (older/left) to b (newer/right)."""
    if a.kind == "cells" and b.kind == "cells":
        res = DiffResult(kind="cells")
        keys = sorted(set(a.cells) | set(b.cells))
        for key in keys:
            va, vb = a.cells.get(key), b.cells.get(key)
            if va is None:
                res.added_cells += 1
                res.changed_cells.append((key[0], key[1], "", vb))
            elif vb is None:
                res.removed_cells += 1
                res.changed_cells.append((key[0], key[1], va, ""))
            elif va != vb:
                res.changed_cells.append((key[0], key[1], va, vb))
        return res
    if a.kind == "text" and b.kind == "text":
        res = DiffResult(kind="text")
        sm = difflib.SequenceMatcher(a=a.lines, b=b.lines, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            if tag in ("delete", "replace"):
                for line in a.lines[i1:i2]:
                    res.deleted += 1
                    if len(res.lines) < max_lines:
                        res.lines.append(("-", line))
            if tag in ("insert", "replace"):
                for line in b.lines[j1:j2]:
                    res.added += 1
                    if len(res.lines) < max_lines:
                        res.lines.append(("+", line))
        return res
    return DiffResult(kind="none")


def summarize_pair(a: FileInfo, b: FileInfo) -> dict:
    """Counts-only summary used on the group view."""
    d = diff_infos(a, b)
    return {"added": d.added, "deleted": d.deleted,
            "changed_cells": len(d.changed_cells),
            "added_cells": d.added_cells,
            "removed_cells": d.removed_cells,
            "kind": d.kind}

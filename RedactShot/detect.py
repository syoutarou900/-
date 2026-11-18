# -*- coding: utf-8 -*-
"""Deterministic detection engine for sensitive candidates in OCR words.

GUI-independent. No display name is hard-coded here; identity lives in
appinfo.py (created by the GUI worker) and this module does not need it.

All detection is deterministic pattern matching only. No fuzzy /
similarity matching is used anywhere in this module.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

CATEGORIES = ["email", "phone", "card", "money", "password", "masked", "custom"]


@dataclass
class Candidate:
    id: int
    category: str
    text: str
    reason_key: str
    reason_params: dict
    x: int
    y: int
    w: int
    h: int
    enabled: bool = True
    manual: bool = False


def normalize(s) -> str:
    """NFKC normalisation followed by casefold."""
    if s is None:
        return ""
    return unicodedata.normalize("NFKC", str(s)).casefold()


def luhn_ok(digits: str) -> bool:
    """Return True iff the digit string passes the Luhn check."""
    if not digits or not digits.isdigit():
        return False
    total = 0
    # From the rightmost digit, double every second digit.
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# ---------------------------------------------------------------------------
# Password label set (13 languages). Stored in raw form and normalised
# on comparison so fullwidth / case variants still match exactly.
# ---------------------------------------------------------------------------
_PASSWORD_LABELS_RAW = [
    "パスワード",
    "パスコード",
    "password",
    "contraseña",
    "密码",
    "密碼",
    "mot de passe",
    "passwort",
    "senha",
    "пароль",
    "parola d'ordine",
    "password",  # Italian also uses "password" (duplicate kept harmless)
    "şifre",
    "sifre",
    "كلمة المرور",
    "kata sandi",
    "비밀번호",
]

# Normalised label -> raw label (first wins)
_PASSWORD_LABELS: Dict[str, str] = {}
for _lbl in _PASSWORD_LABELS_RAW:
    _PASSWORD_LABELS.setdefault(normalize(_lbl), _lbl)
# Labels split by whitespace, for multi-word phrase matching.
_PASSWORD_PHRASES: List[Tuple[str, ...]] = []
for _norm_lbl in _PASSWORD_LABELS:
    _parts = tuple(_norm_lbl.split())
    if _parts:
        _PASSWORD_PHRASES.append(_parts)
# Longest phrases first so multi-word labels win over single-word ones.
_PASSWORD_PHRASES.sort(key=lambda p: -len(p))


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_JP_HYPHEN_RE = re.compile(r"0\d{1,4}-\d{1,4}-\d{4}")
_PHONE_CONT_RE = re.compile(r"(?<!\d)0\d{9,10}(?!\d)")
_PHONE_INTL_RE = re.compile(r"\+\d(?:[ \-]*\d)*")
# Maximal runs of digits / spaces / hyphens that contain at least one digit.
_CARD_RUN_RE = re.compile(r"\d(?:[ \-]*\d)*")
_MONEY_SYMBOL_RE = re.compile(r"[¥$€£₩₹₽￥]\s*\d[\d,]*(?:\.\d+)?")
_MONEY_YEN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s*円")
# After NFKC, ＊ becomes *, ●/•/・/○ are unchanged.
_MASKED_RE = re.compile(r"[●*•・○]{3,}")

_PAD = 2


def _clip_box(x, y, w, h, img_w, img_h):
    """Clip a box to the image rectangle; return (x, y, w, h)."""
    x2 = x + w
    y2 = y + h
    if img_w and img_w > 0:
        x = max(0, min(x, img_w))
        x2 = max(0, min(x2, img_w))
    else:
        x = max(0, x)
        x2 = max(x, x2)
    if img_h and img_h > 0:
        y = max(0, min(y, img_h))
        y2 = max(0, min(y2, img_h))
    else:
        y = max(0, y)
        y2 = max(y, y2)
    return x, y, max(0, x2 - x), max(0, y2 - y)


def _span_to_box(spans, words_in_line, start, end, img_w, img_h):
    """Convert a character span [start, end) to the union box of words.

    spans: list of (span_start, span_end) parallel to words_in_line.
    Returns (x, y, w, h) with a small padding, clipped, or None.
    """
    xs = []
    ys = []
    xe = []
    ye = []
    for (s, e), wd in zip(spans, words_in_line):
        if e > start and s < end:
            xs.append(int(wd["x"]))
            ys.append(int(wd["y"]))
            xe.append(int(wd["x"]) + int(wd["w"]))
            ye.append(int(wd["y"]) + int(wd["h"]))
    if not xs:
        return None
    x = min(xs) - _PAD
    y = min(ys) - _PAD
    w = (max(xe) + _PAD) - x
    h = (max(ye) + _PAD) - y
    return _clip_box(x, y, w, h, img_w, img_h)


def detect(words, img_w, img_h, custom_terms=None, enabled=None):
    """Detect sensitive candidates from OCR word dicts.

    words: iterable of {"text","x","y","w","h","line"} dicts.
    custom_terms: iterable of registered terms (may be None).
    enabled: set of category names to detect; None means all categories.
    Returns a list[Candidate] sorted top-to-bottom, left-to-right.
    """
    if enabled is None:
        enabled_set = set(CATEGORIES)
    else:
        enabled_set = set(enabled)

    custom_norm: List[str] = []
    if custom_terms:
        for term in custom_terms:
            nt = normalize(term).strip()
            if nt:
                custom_norm.append(nt)

    # Group words by line id, preserving input order within grouping step.
    lines: Dict[object, List[dict]] = {}
    line_order: List[object] = []
    all_words: List[dict] = []
    for wd in words or []:
        if wd is None:
            continue
        all_words.append(wd)
        line_id = wd.get("line", 0)
        if line_id not in lines:
            lines[line_id] = []
            line_order.append(line_id)
        lines[line_id].append(wd)

    raw = []  # tuples (sort_key, category, text, reason_key, params, x,y,w,h)

    def add(category, text, reason_key, params, box, sort_key):
        if box is None:
            return
        x, y, w, h = box
        if w <= 0 or h <= 0:
            return
        raw.append((sort_key, category, text, reason_key, dict(params or {}), x, y, w, h))

    # Sort line ids for determinism: numeric ids ascending, others by str.
    def _line_sort_key(lid):
        return (0, lid, "") if isinstance(lid, (int, float)) else (1, 0, str(lid))

    for line_id in sorted(line_order, key=_line_sort_key):
        line_words = sorted(lines[line_id], key=lambda d: (int(d.get("x", 0)), int(d.get("y", 0))))
        if not line_words:
            continue
        norm_texts = [normalize(wd.get("text", "")) for wd in line_words]
        # Build line text: normalised words joined by a single halfwidth space.
        spans: List[Tuple[int, int]] = []
        parts: List[str] = []
        pos = 0
        for i, nt in enumerate(norm_texts):
            if i > 0:
                parts.append(" ")
                pos += 1
            start = pos
            parts.append(nt)
            pos += len(nt)
            spans.append((start, pos))
        line_text = "".join(parts)
        if not line_text:
            continue
        # Representative y for sorting: top of the line.
        line_y = min(int(wd.get("y", 0)) for wd in line_words)

        def box_for(start, end):
            return _span_to_box(spans, line_words, start, end, img_w, img_h)

        # 1. email ------------------------------------------------------
        if "email" in enabled_set:
            for m in _EMAIL_RE.finditer(line_text):
                add("email", m.group(0), "email_pattern", {},
                    box_for(m.start(), m.end()), (line_y, m.start()))

        # 2. phone ------------------------------------------------------
        phone_spans: List[Tuple[int, int]] = []
        if "phone" in enabled_set:
            for m in _PHONE_JP_HYPHEN_RE.finditer(line_text):
                phone_spans.append((m.start(), m.end()))
            for m in _PHONE_CONT_RE.finditer(line_text):
                phone_spans.append((m.start(), m.end()))
            for m in _PHONE_INTL_RE.finditer(line_text):
                digits = re.sub(r"\D", "", m.group(0))
                if 8 <= len(digits) <= 15:
                    # Trim trailing separators are impossible: regex ends
                    # on a digit, so the whole match is usable.
                    phone_spans.append((m.start(), m.end()))
            # De-duplicate identical spans within phone.
            for s, e in sorted(set(phone_spans)):
                add("phone", line_text[s:e], "phone_pattern", {},
                    box_for(s, e), (line_y, s))

        # 3. card -------------------------------------------------------
        if "card" in enabled_set:
            for m in _CARD_RUN_RE.finditer(line_text):
                digits = re.sub(r"\D", "", m.group(0))
                if not (13 <= len(digits) <= 19):
                    continue
                # Do not re-report a pure phone span as a card: digit
                # counts already separate them (phone continuous is
                # 10-11 digits), but guard identical spans explicitly.
                if (m.start(), m.end()) in set(phone_spans):
                    continue
                key = "card_luhn_pass" if luhn_ok(digits) else "card_luhn_fail"
                add("card", m.group(0), key, {"digits": len(digits)},
                    box_for(m.start(), m.end()), (line_y, m.start()))

        # 4. money ------------------------------------------------------
        if "money" in enabled_set:
            money_spans = []
            for m in _MONEY_SYMBOL_RE.finditer(line_text):
                money_spans.append((m.start(), m.end()))
            for m in _MONEY_YEN_RE.finditer(line_text):
                money_spans.append((m.start(), m.end()))
            for s, e in sorted(set(money_spans)):
                add("money", line_text[s:e], "money_pattern", {},
                    box_for(s, e), (line_y, s))

        # 5. masked -----------------------------------------------------
        if "masked" in enabled_set:
            for m in _MASKED_RE.finditer(line_text):
                add("masked", m.group(0), "mask_chars", {},
                    box_for(m.start(), m.end()), (line_y, m.start()))

        # 6. password ---------------------------------------------------
        if "password" in enabled_set:
            consumed = set()  # word indices already used as a label
            n = len(line_words)
            for phrase in _PASSWORD_PHRASES:
                plen = len(phrase)
                if plen > n:
                    continue
                for i in range(0, n - plen + 1):
                    if any((i + k) in consumed for k in range(plen)):
                        continue
                    ok = True
                    for k in range(plen):
                        token = norm_texts[i + k]
                        if k == plen - 1:
                            token = token.rstrip(":").rstrip("：")
                        if token != phrase[k]:
                            ok = False
                            break
                    if not ok:
                        continue
                    for k in range(plen):
                        consumed.add(i + k)
                    label_words = line_words[i:i + plen]
                    lx = min(int(wd["x"]) for wd in label_words)
                    ly = min(int(wd["y"]) for wd in label_words)
                    lxe = max(int(wd["x"]) + int(wd["w"]) for wd in label_words)
                    lye = max(int(wd["y"]) + int(wd["h"]) for wd in label_words)
                    lw = lxe - lx
                    lh = lye - ly
                    right_words = line_words[i + plen:]
                    if right_words:
                        rx = min(int(wd["x"]) for wd in right_words)
                        ry = min(int(wd["y"]) for wd in right_words)
                        rxe = max(int(wd["x"]) + int(wd["w"]) for wd in right_words)
                        rye = max(int(wd["y"]) + int(wd["h"]) for wd in right_words)
                        box = _clip_box(rx - _PAD, ry - _PAD,
                                        (rxe + _PAD) - (rx - _PAD),
                                        (rye + _PAD) - (ry - _PAD),
                                        img_w, img_h)
                    else:
                        est_w = max(160, lw * 3)
                        est_h = lh
                        # Stacked layout: if a word sits just below the
                        # label and roughly under it, the field is most
                        # likely below (e.g. login forms). Prefer a box
                        # below the label that covers that content.
                        below = []
                        for wd in all_words:
                            wx = int(wd.get("x", 0)); wy = int(wd.get("y", 0))
                            wxe = wx + int(wd.get("w", 0)); wye = wy + int(wd.get("h", 0))
                            if wy < lye - 2:
                                continue
                            if wy - lye > max(48, lh * 3):
                                continue
                            if wxe < lx - 8 or wx > lxe + 8:
                                continue
                            below.append((wx, wy, wxe, wye))
                        if below:
                            bx = lx
                            by = lye + 4
                            bw = max(est_w, max(b[2] for b in below) - lx + 8)
                            bh = max(lh + 8, max(b[3] for b in below) - by + 6)
                            box = _clip_box(bx, by, bw, bh, img_w, img_h)
                        else:
                            remaining = (img_w - lxe) if img_w else est_w
                            if remaining < 40:
                                # Place below the label with the same size.
                                box = _clip_box(lx, lye, est_w, est_h, img_w, img_h)
                            else:
                                box = _clip_box(lxe, ly, est_w, est_h, img_w, img_h)
                    label_text = " ".join(
                        str(wd.get("text", "")) for wd in label_words
                    )
                    add("password", label_text, "password_estimate", {},
                        box, (line_y, spans[i][0]))

        # 7. custom -----------------------------------------------------
        if "custom" in enabled_set and custom_norm:
            for nt in custom_norm:
                start = 0
                while True:
                    idx = line_text.find(nt, start)
                    if idx < 0:
                        break
                    add("custom", line_text[idx:idx + len(nt)], "custom_term",
                        {"term": nt}, box_for(idx, idx + len(nt)),
                        (line_y, idx))
                    start = idx + max(1, len(nt))

    # De-duplicate: same range + same category -> one candidate.
    seen = set()
    uniq = []
    for item in raw:
        _, category, _, _, _, x, y, w, h = item
        key = (category, x, y, w, h)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)

    # Deterministic ordering: by sort key (line top, span start), then
    # category order, then position.
    cat_index = {c: i for i, c in enumerate(CATEGORIES)}
    uniq.sort(key=lambda it: (it[0][0], it[0][1], cat_index.get(it[1], 99), it[5], it[6]))

    candidates: List[Candidate] = []
    for idx, (_, category, text, reason_key, params, x, y, w, h) in enumerate(uniq, start=1):
        candidates.append(Candidate(
            id=idx, category=category, text=text, reason_key=reason_key,
            reason_params=params, x=int(x), y=int(y), w=int(w), h=int(h),
        ))
    return candidates

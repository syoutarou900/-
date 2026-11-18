# -*- coding: utf-8 -*-
"""Learning from corrections — ContextStruct v2 (user point 7).

HONEST SCOPE: this is in-context / dictionary learning, NOT model retraining.
The VLM weights never change. What the app learns is:
  1. a correction store (learning.jsonl) — every confirmed human edit;
  2. keyword aliases — a word found next to a corrected value in the source
     text becomes a new keyword for that field in the profile (persisted,
     visible in the profile editor);
  3. few-shot examples — the most recent corrections for the active profile
     are injected into the VLM prompt;
  4. per-vendor profile memory — the profile last confirmed for a detected
     vendor is auto-suggested next time that vendor appears.

The heavy engines themselves (llama.cpp, Tesseract, OpenCV) are native
C/C++ programs orchestrated by Python; that combination is what raises
quality — the learning layer only steers them with the user's own data.
"""
import os, re, json, difflib, datetime, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from context_core import get_app_dir

VENDOR_HINTS = ("取引先", "請求先", "納入先", "宛先", "vendor", "customer", "bill to", "supplier", "会社名")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def learning_path(base_dir=None):
    return os.path.join(base_dir or get_app_dir(), "learning.jsonl")


def save_correction(profile_name, field_column, original, corrected, source_snippet="", base_dir=None):
    """Append one confirmed correction. Returns the stored record."""
    rec = {"timestamp": _now(), "profile": profile_name, "field": field_column,
           "original": original or "", "corrected": corrected or "",
           "source_snippet": (source_snippet or "")[:300]}
    p = learning_path(base_dir)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def load_corrections(base_dir=None):
    p = learning_path(base_dir)
    out = []
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        pass
    return out


def recent_corrections(profile_name, limit=5, base_dir=None):
    recs = [r for r in load_corrections(base_dir) if r.get("profile") == profile_name]
    return recs[-limit:]


_SEPARATORS = " \t:：=|/・,、"


def learn_alias(profile, field_column, corrected_value, source_text):
    """If the corrected value appears in the source text preceded by a word
    that is not yet a keyword of the field, add that word as a keyword alias.
    Mutates the profile's field; returns the learned word or None."""
    if not corrected_value or not source_text:
        return None
    fdef = next((f for f in profile.fields if f.target_column == field_column), None)
    if fdef is None:
        return None
    existing = {k.lower() for k in fdef.keyword_list()}
    for line in str(source_text).splitlines():
        idx = line.find(str(corrected_value))
        if idx < 0:
            continue
        before = line[:idx].rstrip(_SEPARATORS)
        if not before:
            continue
        # last token before the value (split on whitespace / colons / brackets)
        token = re.split(r"[\s:：=|/・,、()（）\[\]]+", before)[-1].strip()
        if not token or len(token) > 30:
            continue
        if token.lower() in existing:
            return None  # already known — nothing to learn
        if re.fullmatch(r"[\d,.\-]+", token):
            continue  # a number is not a keyword
        if any(kw and kw.lower() in token.lower() for kw in existing):
            return None  # token already contains a known keyword
        fdef.keywords = (fdef.keywords + "," + token) if fdef.keywords else token
        return token
    return None


# ------------------------------------------------------- vendor memory ----
def vendor_memory_path(base_dir=None):
    return os.path.join(base_dir or get_app_dir(), "vendor_profiles.json")


def _load_vendor_memory(base_dir=None):
    p = vendor_memory_path(base_dir)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def remember_vendor_profile(vendor, profile_name, base_dir=None):
    vendor = (vendor or "").strip()
    if not vendor:
        return
    mem = _load_vendor_memory(base_dir)
    mem[vendor] = {"profile": profile_name, "timestamp": _now()}
    p = vendor_memory_path(base_dir)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(mem, f, ensure_ascii=False, indent=2)


def profile_for_vendor(vendor, base_dir=None):
    vendor = (vendor or "").strip()
    if not vendor:
        return None
    mem = _load_vendor_memory(base_dir)
    if vendor in mem:
        return mem[vendor].get("profile")
    # fuzzy: closest remembered vendor name
    best, best_r = None, 0.0
    for name, rec in mem.items():
        r = difflib.SequenceMatcher(None, vendor, name).ratio()
        if r > best_r:
            best, best_r = rec.get("profile"), r
    return best if best_r >= 0.9 else None


def detect_vendor(rows, profile):
    """Return the value of the vendor-like field of the first row, if any."""
    if not rows:
        return ""
    for f in profile.fields:
        hay = (f.display_name + " " + f.target_column).lower()
        if any(h in hay for h in VENDOR_HINTS):
            fr = rows[0].get(f.target_column)
            v = fr.value if fr is not None and hasattr(fr, "value") else (str(fr) if fr else "")
            if v:
                return v
    return ""

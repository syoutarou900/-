# -*- coding: utf-8 -*-
"""Local Tesseract OCR wrapper.

GUI-independent. No display name is hard-coded here; the environment
variable name below is part of the interface contract, not a display
name.
"""

from __future__ import annotations

import csv
import io
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ENV_TESSERACT = "REDACTSHOT_TESSERACT"
LEGACY_ENV_TESSERACT = "BLURSHIELD_TESSERACT"


class OcrUnavailable(Exception):
    """Raised when no usable Tesseract executable can be found / run."""


_UI_TO_TESSERACT = {
    "ja": "jpn",
    "en": "eng",
    "es": "spa",
    "zh": "chi_sim",
    "fr": "fra",
    "de": "deu",
    "pt": "por",
    "ru": "rus",
    "it": "ita",
    "tr": "tur",
    "ar": "ara",
    "id": "ind",
    "ko": "kor",
}


def _app_dir() -> Path:
    return Path(__file__).resolve().parent


def _find_tesseract():
    """Search in contract order; return a path/command string or None."""
    # 1. Environment variable.
    env_val = os.environ.get(ENV_TESSERACT) or os.environ.get(LEGACY_ENV_TESSERACT)
    if env_val:
        env_val = env_val.strip()
        if env_val:
            if Path(env_val).exists():
                return env_val
            found = shutil.which(env_val)
            if found:
                return found
            # An explicitly configured but missing path is not usable;
            # fall through to the other locations.
    # 2. Adjacent bundled binary.
    app_dir = _app_dir()
    if os.name == "nt" or sys.platform.startswith("win"):
        adjacent = app_dir / "tesseract" / "tesseract.exe"
    else:
        adjacent = app_dir / "tesseract" / "tesseract"
    if adjacent.exists():
        return str(adjacent)
    # Also accept the .exe name on any platform (e.g. cross checks).
    adjacent_exe = app_dir / "tesseract" / "tesseract.exe"
    if adjacent_exe.exists():
        return str(adjacent_exe)
    # 3. PATH.
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    return None


def _tessdata_prefix():
    """Return the adjacent tessdata directory if one exists, else None."""
    app_dir = _app_dir()
    candidates = [
        app_dir / "tessdata",
        app_dir / "tesseract" / "tessdata",
    ]
    for cand in candidates:
        if cand.is_dir():
            return str(cand)
    return None


def languages_for_ui(ui_lang) -> list:
    """Tesseract language list: always jpn+eng, plus the UI language."""
    langs = ["jpn", "eng"]
    if ui_lang:
        primary = str(ui_lang).replace("_", "-").split("-")[0].strip().lower()
        mapped = _UI_TO_TESSERACT.get(primary)
        # Also allow passing a tesseract code directly.
        if mapped is None and primary in _UI_TO_TESSERACT.values():
            mapped = primary
        if mapped and mapped not in langs:
            langs.append(mapped)
    return langs


def _parse_tsv(output: str) -> list:
    words = []
    if not output:
        return words
    reader = csv.DictReader(io.StringIO(output), delimiter="\t", quoting=csv.QUOTE_MINIMAL)
    if reader.fieldnames is None:
        return words
    line_id_by_key = {}
    next_line_id = 0
    for row in reader:
        if row is None:
            continue
        text = (row.get("text") or "")
        if not text.strip():
            continue
        try:
            conf = float(row.get("conf", -1))
        except (TypeError, ValueError):
            continue
        if conf < 0:
            continue
        # Level 5 is a word; if level is present and not 5, skip it.
        level = row.get("level")
        if level not in (None, "", "5"):
            try:
                if int(level) != 5:
                    continue
            except (TypeError, ValueError):
                pass
        try:
            x = int(float(row.get("left", 0)))
            y = int(float(row.get("top", 0)))
            w = int(float(row.get("width", 0)))
            h = int(float(row.get("height", 0)))
        except (TypeError, ValueError):
            continue
        key = (row.get("block_num"), row.get("par_num"), row.get("line_num"))
        if key not in line_id_by_key:
            line_id_by_key[key] = next_line_id
            next_line_id += 1
        words.append({
            "text": text,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "line": line_id_by_key[key],
        })
    return words


# ---------------------------------------------------------------------------
# Post-processing of the raw word list (added after field testing on
# synthetic screenshots, see quality/REPORT.md):
#
# 1. Tesseract frequently splits a contiguous CJK run into several
#    "words" (e.g. a name read as two words, a company name as eight).
#    Downstream detection joins words with spaces, so a registered term
#    written without spaces would never match.  Merge same-line
#    neighbours when BOTH contain a CJK character and the horizontal
#    gap is at most 0.6x the smaller height.  Latin words are never
#    merged (both sides must contain CJK), so real spaces survive.
# 2. With the Japanese language data, Tesseract often returns the yen
#    sign as a backslash ("\140,800").  In Japanese text U+005C is the
#    yen sign, so a leading backslash directly before a digit is
#    normalised to "¥" when Japanese OCR data was used.
# ---------------------------------------------------------------------------
_CJK_RE = re.compile(r"[぀-ヿ㐀-鿿豈-﫿＀-｠]")
_YEN_LEAD_RE = re.compile(r"^\\(?=[0-9])")


def _merge_cjk_words(words):
    by_line = {}
    order = []
    for wd in words or []:
        lid = wd.get("line", 0)
        if lid not in by_line:
            by_line[lid] = []
            order.append(lid)
        by_line[lid].append(wd)
    out = []
    for lid in order:
        line = sorted(by_line[lid], key=lambda d: (int(d.get("x", 0)), int(d.get("y", 0))))
        cur = None
        for wd in line:
            if cur is not None:
                gap = int(wd["x"]) - (int(cur["x"]) + int(cur["w"]))
                if (0 <= gap <= 0.6 * min(int(cur["h"]), int(wd["h"]))
                        and _CJK_RE.search(str(cur.get("text", "")))
                        and _CJK_RE.search(str(wd.get("text", "")))):
                    x2 = max(int(cur["x"]) + int(cur["w"]), int(wd["x"]) + int(wd["w"]))
                    y1 = min(int(cur["y"]), int(wd["y"]))
                    y2 = max(int(cur["y"]) + int(cur["h"]), int(wd["y"]) + int(wd["h"]))
                    cur = {"text": str(cur["text"]) + str(wd["text"]),
                           "x": int(cur["x"]), "y": y1,
                           "w": x2 - int(cur["x"]), "h": y2 - y1,
                           "line": lid}
                    continue
            if cur is not None:
                out.append(cur)
            cur = dict(wd)
        if cur is not None:
            out.append(cur)
    return out


def _normalize_yen_sign(words):
    out = []
    for wd in words or []:
        wd = dict(wd)
        text = str(wd.get("text", ""))
        if _YEN_LEAD_RE.match(text):
            wd["text"] = "¥" + text[1:]
        out.append(wd)
    return out


def run_ocr(image_path, ui_lang) -> list:
    """Run Tesseract on *image_path* and return a list of word dicts.

    Raises OcrUnavailable when no Tesseract executable is found.
    """
    exe = _find_tesseract()
    if not exe:
        raise OcrUnavailable(
            "Tesseract executable not found (checked "
            f"{ENV_TESSERACT}, adjacent tesseract/ directory, and PATH)"
        )
    langs = languages_for_ui(ui_lang)
    # TSV output is requested with "-c tessedit_create_tsv=1" instead of
    # the "tsv" config-file argument: a config file only works when the
    # tessdata directory contains configs/tsv, which traineddata-only
    # bundles (e.g. the one shipped with TranscribeGuard) do not have --
    # there Tesseract silently falls back to plain text and no words
    # are returned at all.  The -c form works in both layouts.
    cmd = [exe, str(image_path), "stdout", "-l", "+".join(langs),
           "-c", "tessedit_create_tsv=1"]

    env = dict(os.environ)
    prefix = _tessdata_prefix()
    if prefix:
        env["TESSDATA_PREFIX"] = prefix

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except OSError as exc:
        raise OcrUnavailable(f"failed to run Tesseract: {exc}") from exc

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise OcrUnavailable(
            f"Tesseract failed with exit code {proc.returncode}"
            + (f": {stderr}" if stderr else "")
        )
    words = _merge_cjk_words(_parse_tsv(proc.stdout or ""))
    if "jpn" in langs:
        words = _normalize_yen_sign(words)
    return words

# -*- coding: utf-8 -*-
"""Ensemble extraction + verification — ContextStruct v2 (accuracy upgrade).

Multiple engines read the same document, each returning
{target_column: (value, confidence)} rows:
  * PDF text layer / typed text  -> rule engine (context_core.extract_document)
  * Tesseract OCR                -> rule engine over OCR text of the ORIGINAL
                                    image and of the preprocessed variants
                                    (enhanced / binarized) — separate voters
  * easyocr / paddleocr          -> optional voters, only if importable
  * local VLM (llama.cpp)        -> image understanding, read TWICE with two
                                    prompt phrasings (self-consistency)
  * external API VLM             -> optional cloud engine (maximum accuracy)

A merger votes per field: values that agree (after normalization) across
>= 2 engines are boosted to 97-99; a single engine keeps its own confidence;
on disagreement the most-supported value wins but its confidence is capped
and the field is flagged for the verification pass.

Verification pass:
  (a) arithmetic checks (qty x unit price vs total, item sum vs total,
      consumption-tax 8%/10% pattern) — failures lower confidence;
  (b) targeted VLM re-read of disputed / failed fields with a
      field-specific question (vlm_local.run_field_reread);
  (c) master matching against a product/vendor master CSV — a fuzzy snap
      (>= 0.85) to a master entry boosts confidence.
"""
import os, csv, difflib, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from context_core import (FieldResult, extract_document, format_value, ocr_available,
                          ocr_image)
import vlm_local

AGREE_MIN, AGREE_MAX = 97, 99
DISAGREE_CAP = 65


def normalize_value(value, field_type):
    if value is None:
        return ""
    v = format_value(str(value), field_type) if field_type else str(value).strip()
    if field_type in (None, "text"):
        v = " ".join(str(value).strip().split()).casefold()
    return v


# ---------------------------------------------------------------- merger ----
def merge_engine_rows(engine_rows, profile):
    """engine_rows: {engine_name: [ {col: FieldResult}, ... ]}.
    Returns (merged_rows, report) where report = {
        'disputed': [(row_index, col), ...],
        'fields': {(row_index, col): {'engines': [...], 'agreed': bool,
                                      'disagreement': bool}}}"""
    ftypes = {f.target_column: f.field_type for f in profile.fields}
    cols = [f.target_column for f in profile.fields]
    n_rows = 0
    for rows in engine_rows.values():
        n_rows = max(n_rows, len(rows or []))
    if n_rows == 0:
        n_rows = 1
    merged, report = [], {"disputed": [], "fields": {}}
    for ri in range(n_rows):
        row = {}
        for col in cols:
            cands = []  # (engine, raw_value, norm, conf, snippet)
            for eng, rows in engine_rows.items():
                if not rows or ri >= len(rows):
                    continue
                fr = rows[ri].get(col)
                if fr is None:
                    continue
                val = fr.value if hasattr(fr, "value") else str(fr)
                conf = fr.confidence if hasattr(fr, "confidence") else 50
                if val is None or str(val).strip() == "":
                    continue
                norm = normalize_value(val, ftypes.get(col, "text"))
                if norm == "":
                    continue
                cands.append((eng, str(val), norm, int(conf), getattr(fr, "snippet", "") or ""))
            if not cands:
                row[col] = FieldResult("", 0, "not_found", "")
                report["fields"][(ri, col)] = {"engines": [], "agreed": False, "disagreement": False}
                continue
            groups = {}
            for c in cands:
                groups.setdefault(c[2], []).append(c)
            # winner: most supporters, then highest total confidence
            winner_norm, winner = max(groups.items(), key=lambda kv: (len(kv[1]), sum(x[3] for x in kv[1])))
            disagreement = len(groups) > 1
            best = max(winner, key=lambda x: x[3])
            engines = [x[0] for x in winner]
            if len(winner) >= 2:
                avg = sum(x[3] for x in winner) / len(winner)
                conf = max(AGREE_MIN, min(AGREE_MAX, int(round(avg)) + 5))
                reason = f"agreement x{len(winner)} [{', '.join(engines)}]"
                agreed = True
            else:
                conf = best[3]
                reason = f"{best[0]}: single"
                agreed = False
            if disagreement:
                conf = min(conf, DISAGREE_CAP)
                reason += " + disagreement (verify)"
                report["disputed"].append((ri, col))
            row[col] = FieldResult(best[1], conf, reason, best[4])
            report["fields"][(ri, col)] = {"engines": engines, "agreed": agreed, "disagreement": disagreement}
        merged.append(row)
    return merged, report


# ------------------------------------------------------------- arithmetic ----
def _num(fr):
    if fr is None:
        return None
    v = fr.value if hasattr(fr, "value") else fr
    try:
        return float(str(v).replace(",", "")) if str(v).strip() != "" else None
    except Exception:
        return None


def _find_col(profile, hints):
    for f in profile.fields:
        hay = (f.display_name + " " + f.target_column).lower()
        if any(h.lower() in hay for h in hints):
            return f.target_column
    return None


def _penalize(fr, points, reason):
    if fr is None or not fr.value:
        return
    fr.confidence = max(5, fr.confidence - points)
    if reason not in fr.reason:
        fr.reason = (fr.reason + " + " + reason).strip(" +")


def arithmetic_validation(rows, profile, tol_abs=2.0, tol_ratio=0.01):
    """Mutates FieldResults (lowers confidence + adds reason) on failed checks.
    Returns {'passed': bool, 'checks': [str], 'failed_fields': [(ri, col)]}.
    'passed' is True when nothing checkable exists (nothing failed)."""
    checks, failed = [], []
    qty_c = _find_col(profile, ["数量", "qty", "quantity"])
    unit_c = _find_col(profile, ["単価", "unit price"])
    total_c = _find_col(profile, ["合計", "請求金額", "total", "amount due"])
    subtotal_c = _find_col(profile, ["小計", "subtotal"])
    tax_c = _find_col(profile, ["消費税", "税額", "tax"])
    if total_c == subtotal_c:
        total_c = None

    def tol(expected):
        return max(tol_abs, abs(expected) * tol_ratio)

    # qty x unit price summed over rows ~= total
    if qty_c and unit_c and total_c and rows:
        s, any_pair = 0.0, False
        for r in rows:
            q, u = _num(r.get(qty_c)), _num(r.get(unit_c))
            if q is not None and u is not None:
                s += q * u
                any_pair = True
        total = _num(rows[0].get(total_c))
        if any_pair and total is not None:
            if abs(s - total) <= tol(total):
                checks.append("qty*unit ~= total: OK")
            else:
                checks.append(f"qty*unit ({s}) != total ({total}): FAIL")
                for ri, r in enumerate(rows):
                    _penalize(r.get(qty_c), 10, "arith_fail")
                    _penalize(r.get(unit_c), 10, "arith_fail")
                    _penalize(r.get(total_c), 25, "arith_fail: qty*unit != total")
                    failed.append((ri, total_c))
    # consumption tax pattern: tax ~= subtotal * 10% or * 8%; total ~= subtotal + tax
    if subtotal_c and tax_c and rows:
        sub, tax = _num(rows[0].get(subtotal_c)), _num(rows[0].get(tax_c))
        if sub is not None and tax is not None:
            ok_rate = any(abs(tax - sub * r) <= tol(sub * r) for r in (0.10, 0.08))
            if ok_rate:
                checks.append("tax rate 8%/10%: OK")
            else:
                checks.append(f"tax ({tax}) != subtotal ({sub}) x 8%/10%: FAIL")
                for ri, r in enumerate(rows):
                    _penalize(r.get(tax_c), 20, "arith_fail: tax rate")
                    failed.append((ri, tax_c))
            if total_c:
                total = _num(rows[0].get(total_c))
                if total is not None and abs(sub + tax - total) > tol(total):
                    checks.append(f"subtotal+tax ({sub + tax}) != total ({total}): FAIL")
                    for ri, r in enumerate(rows):
                        _penalize(r.get(total_c), 20, "arith_fail: subtotal+tax != total")
                        failed.append((ri, total_c))
                elif total is not None:
                    checks.append("subtotal+tax ~= total: OK")
    return {"passed": len(failed) == 0, "checks": checks, "failed_fields": failed}


# ---------------------------------------------------------------- master ----
def load_master(path):
    """Master CSV: uses columns named code/name when present, else the first
    two columns. Returns [{'code':..., 'name':...}, ...]."""
    entries = []
    if not path or not os.path.isfile(path):
        return entries
    with open(path, encoding="utf-8-sig", errors="ignore", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return entries
    header = [c.strip().lower() for c in rows[0]]
    code_i = header.index("code") if "code" in header else 0
    name_i = header.index("name") if "name" in header else (1 if len(header) > 1 else 0)
    body = rows[1:] if ("code" in header or "name" in header) else rows
    for r in body:
        if not r:
            continue
        code = r[code_i].strip() if code_i < len(r) else ""
        name = r[name_i].strip() if name_i < len(r) else ""
        if code or name:
            entries.append({"code": code, "name": name})
    return entries


NAME_HINTS = ("商品名", "品名", "名称", "取引先", "請求先", "product", "name", "vendor", "customer", "item")
CODE_HINTS = ("コード", "型番", "code", "sku", "品番")


def master_match(rows, profile, master, threshold=0.85):
    """Snap name/code fields to master entries (fuzzy, difflib). Mutates rows.
    Returns the number of fields snapped/matched."""
    if not master:
        return 0
    names = [e["name"] for e in master if e["name"]]
    codes = [e["code"] for e in master if e["code"]]
    count = 0
    for f in profile.fields:
        hay = (f.display_name + " " + f.target_column).lower()
        is_code = any(h in hay for h in CODE_HINTS)
        is_name = (not is_code) and any(h in hay for h in NAME_HINTS)
        if not (is_code or is_name):
            continue
        pool = codes if is_code else names
        if not pool:
            continue
        for r in rows:
            fr = r.get(f.target_column)
            if fr is None or not fr.value:
                continue
            best, best_ratio = None, 0.0
            for cand in pool:
                ratio = difflib.SequenceMatcher(None, str(fr.value).casefold(), cand.casefold()).ratio()
                if ratio > best_ratio:
                    best, best_ratio = cand, ratio
            if best is not None and best_ratio >= threshold:
                if best != fr.value:
                    fr.value = best
                fr.confidence = min(99, fr.confidence + (5 if best_ratio >= 0.999 else 10))
                if "master matched" not in fr.reason:
                    fr.reason = (fr.reason + " + master matched").strip(" +")
                count += 1
    return count


# ------------------------------------------------------- verification pass ----
def verify_and_reread(rows, profile, image_path, disputed, runner=None, model_key=None):
    """Targeted VLM re-read for disputed/failed fields. runner is injectable
    (tests). Returns the list of (row_index, col) actually re-read."""
    if not image_path or not disputed:
        return []
    done, seen = [], set()
    for ri, col in disputed:
        if (ri, col) in seen or ri >= len(rows):
            continue
        seen.add((ri, col))
        try:
            fr = vlm_local.run_field_reread(image_path, profile, col, runner=runner, model_key=model_key)
        except Exception:
            fr = None
        if fr is None or not fr.value:
            continue
        current = rows[ri].get(col)
        if current is not None and current.value == fr.value:
            current.confidence = max(current.confidence, 96)
            current.reason = (current.reason + " + verify_reread agreed").strip(" +")
        else:
            rows[ri][col] = FieldResult(fr.value, min(fr.confidence, 90),
                                         fr.reason + " (verify_reread replaced)", fr.snippet)
        done.append((ri, col))
    return done


# ------------------------------------------------------------- collection ----
def optional_ocr_text(image_path):
    """easyocr / paddleocr as extra voters — LAZY import only (they pull in
    torch and are deliberately NOT in requirements). Returns text or None."""
    try:
        import easyocr  # noqa
        reader = easyocr.Reader(["ja", "en"], gpu=False, verbose=False)
        res = reader.readtext(image_path, detail=0)
        if res:
            return "\n".join(res)
    except Exception:
        pass
    try:
        from paddleocr import PaddleOCR  # noqa
        ocr = PaddleOCR(use_angle_cls=True, lang="japan", show_log=False)
        res = ocr.ocr(image_path, cls=True)
        lines = []
        for page in (res or []):
            for item in (page or []):
                try:
                    lines.append(item[1][0])
                except Exception:
                    pass
        if lines:
            return "\n".join(lines)
    except Exception:
        pass
    return None


def collect_engine_rows(profile, text="", source_path=None, image_path=None, settings=None,
                        vlm_runner=None, use_vlm=False, few_shot=None, ocr_fn=None,
                        text_engine_name="text_rules", include_ocr_variants=True):
    """Gather rows from every available engine. Missing engines are skipped
    silently — the merger works with whatever voted."""
    settings = settings or {}
    engines = {}
    if text and text.strip():
        try:
            engines[text_engine_name] = extract_document(text, profile)
        except Exception:
            pass
    # --- OCR voters: original + preprocessed variants (dirty FAX / handwriting path)
    if image_path and os.path.isfile(image_path):
        ocr_texts = {}
        if ocr_available():
            lang_hint = settings.get("ocr_lang", "jpn+eng")
            fn = ocr_fn or (lambda im: ocr_image(im, lang_hint))
            try:
                from PIL import Image
                targets = [("orig", image_path)]
                if include_ocr_variants:
                    try:
                        import preprocess
                        for vname, vpath in preprocess.preprocess_to_files(image_path).items():
                            if vname in ("enhanced", "binarized"):
                                targets.append((vname, vpath))
                    except Exception:
                        pass
                for vname, vpath in targets:
                    try:
                        t = fn(Image.open(vpath))
                    except Exception:
                        t = None
                    if t and t.strip():
                        ocr_texts[vname] = t
            except Exception:
                pass
        for vname, t in ocr_texts.items():
            try:
                engines[f"ocr_{vname}"] = extract_document(t, profile)
            except Exception:
                pass
        if settings.get("optional_ocr"):
            t = optional_ocr_text(image_path)
            if t and t.strip():
                try:
                    engines["optional_ocr"] = extract_document(t, profile)
                except Exception:
                    pass
    # --- local VLM: self-consistency double read (two phrasings)
    if use_vlm and image_path:
        for variant, name in ((0, "vlm_p1"), (1, "vlm_p2")):
            try:
                engines[name] = vlm_local.run_local_vlm(
                    image_path, profile, runner=vlm_runner, prompt_variant=variant,
                    few_shot=few_shot, model_key=(settings.get("vlm_model_size") or None))
            except Exception:
                pass
    # --- external API VLM (cloud maximum) as one more voter
    if image_path and settings.get("vlm_use_api") and settings.get("vlm_endpoint") and settings.get("vlm_model"):
        try:
            from context_core import call_vlm
            result = call_vlm(image_path, profile, settings)
            if result:
                engines["api_cloud"] = vlm_local.vlm_data_to_rows({"fields": result}, profile)
        except Exception:
            pass
    return engines


def run_pipeline(profile, text="", source_path=None, image_path=None, settings=None,
                 vlm_runner=None, use_vlm=False, few_shot=None, master=None, ocr_fn=None,
                 text_engine_name="text_rules", verify=True):
    """Full v2 pipeline: collect -> merge -> master -> arithmetic -> targeted
    re-read of disputed/failed fields. Returns (rows, info dict)."""
    engines = collect_engine_rows(profile, text=text, source_path=source_path,
                                  image_path=image_path, settings=settings,
                                  vlm_runner=vlm_runner, use_vlm=use_vlm,
                                  few_shot=few_shot, ocr_fn=ocr_fn,
                                  text_engine_name=text_engine_name)
    rows, report = merge_engine_rows(engines, profile)
    snapped = master_match(rows, profile, master) if master else 0
    arith = arithmetic_validation(rows, profile)
    reread = []
    if verify and image_path:
        disputed = list(dict.fromkeys(report["disputed"] + arith["failed_fields"]))
        if disputed:
            reread = verify_and_reread(rows, profile, image_path, disputed,
                                       runner=vlm_runner,
                                       model_key=(settings or {}).get("vlm_model_size") or None)
    info = {"engines": sorted(engines.keys()), "report": report, "arithmetic": arith,
            "master_snapped": snapped, "reread": reread}
    return rows, info

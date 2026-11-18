# -*- coding: utf-8 -*-
"""Complete automation (user point B) — ContextStruct v2.

Watch-folder / batch unattended processing:
  file -> preprocessing/ensemble extraction -> master match -> arithmetic
  validation -> if EVERY field confidence >= threshold AND arithmetic
  checks pass: append rows to the output file (.xlsx or .csv), write an
  audit record (audit_log.jsonl), move the source file to the DONE folder.
  Otherwise: move the source to the REVIEW folder for a human to open in
  the normal confirmation mode. Nothing is ever registered silently
  without an audit record.

This module is Qt-free so the whole flow is unit-testable headlessly.
The injectable `extract_fn(path, profile, settings) -> rows` lets tests
(and the GUI) plug in the real ensemble pipeline.
"""
import os, json, csv, shutil, datetime, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from context_core import (FieldResult, rows_to_dicts, extract_text_from_pdf,
                          extract_text_from_image_file, extract_document, get_app_dir)
import ensemble as ensemble_mod
import integrations as integrations_mod

SUPPORTED_EXTS = (".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".txt", ".csv")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def default_extract(path, profile, settings=None):
    """Default pipeline for unattended mode: fast text engines + OCR variants
    (ensemble), with the local VLM added when it is downloaded and the
    extraction mode asks for it. Returns FieldResult rows."""
    settings = settings or {}
    ext = os.path.splitext(path)[1].lower()
    text, image_path = "", None
    if ext == ".pdf":
        text, _ = extract_text_from_pdf(path)
        try:
            import vlm_local
            image_path = vlm_local.prepare_vlm_image(path, dpi=200)
        except Exception:
            image_path = None
    elif ext in (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"):
        image_path = path
        t = extract_text_from_image_file(path)
        text = t or ""
    elif ext in (".txt", ".csv"):
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
    use_vlm = False
    if image_path and settings.get("extract_mode") in ("auto", "local_vlm"):
        try:
            import vlm_local
            key = vlm_local.selected_model_key(settings)
            use_vlm = vlm_local.model_status(model_key=key)["complete"] and bool(vlm_local.find_runtime_binary())
        except Exception:
            use_vlm = False
    master = None
    if settings.get("master_csv"):
        master = ensemble_mod.load_master(settings["master_csv"])
    rows, _info = ensemble_mod.run_pipeline(
        profile, text=text, image_path=image_path, settings=settings,
        use_vlm=use_vlm, master=master,
        text_engine_name="pdf_text" if ext == ".pdf" else "text_rules")
    return rows


def evaluate(rows, profile, threshold):
    """Acceptance test: every field of every row >= threshold.
    Returns (ok, min_confidence, missing_or_low list)."""
    low, min_conf = [], 100
    for ri, row in enumerate(rows):
        for f in profile.fields:
            fr = row.get(f.target_column, FieldResult())
            c = fr.confidence if fr else 0
            min_conf = min(min_conf, c)
            if c < threshold:
                low.append((ri, f.target_column, c))
    if not rows:
        return False, 0, low
    return (len(low) == 0), min_conf, low


def append_output(rows, profile, output_path):
    """Append rows to .xlsx (created with the profile header when absent)
    or .csv. Returns the output path."""
    dicts = rows_to_dicts(rows, profile)
    cols = [f.target_column for f in profile.fields]
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    if output_path.lower().endswith(".csv"):
        exists = os.path.isfile(output_path) and os.path.getsize(output_path) > 0
        with open(output_path, "a", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            if not exists:
                w.writeheader()
            w.writerows(dicts)
    else:
        from openpyxl import Workbook, load_workbook
        if os.path.isfile(output_path):
            wb = load_workbook(output_path)
            ws = wb.active
            if ws.max_row == 1 and all((c.value in (None, "")) for c in ws[1]):
                ws.append(cols)
        else:
            wb = Workbook()
            ws = wb.active
            ws.append(cols)
        for d in dicts:
            ws.append([d[c] for c in cols])
        wb.save(output_path)
    return output_path


def write_audit(record, app_dir=None):
    p = os.path.join(app_dir or get_app_dir(), "audit_log.jsonl")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return p


def _unique_dest(folder, filename):
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, filename)
    if os.path.exists(dest):
        stem, ext = os.path.splitext(filename)
        i = 2
        while os.path.exists(dest):
            dest = os.path.join(folder, f"{stem}_{i}{ext}")
            i += 1
    return dest


def process_file_auto(path, profile, cfg, extract_fn=None, app_dir=None):
    """Process one file unattended.
    cfg keys: output_path, done_folder, review_folder, threshold (default 90),
              settings (dict passed to the extractor).
    Returns a result dict with 'decision' in {'accepted', 'review', 'error'}."""
    extract_fn = extract_fn or default_extract
    settings = cfg.get("settings") or {}
    threshold = int(cfg.get("threshold", 90) or 90)
    base = os.path.basename(path)
    try:
        rows = extract_fn(path, profile, settings)
    except Exception as e:
        rows = []
        err = str(e)
    else:
        err = ""
    if err or not rows:
        arith = {"passed": False, "checks": [f"extract error: {err}"] if err else ["no rows"]}
        ok, min_conf, low = False, 0, []
    else:
        arith = ensemble_mod.arithmetic_validation(rows, profile)
        ok, min_conf, low = evaluate(rows, profile, threshold)
    accepted = bool(ok and arith["passed"])
    values = rows_to_dicts(rows, profile) if rows else []
    confidences = {}
    if rows:
        for ri, row in enumerate(rows):
            for f in profile.fields:
                fr = row.get(f.target_column, FieldResult())
                confidences[f"{ri}:{f.target_column}"] = fr.confidence if fr else 0
    dest = ""
    destination = ""
    if accepted:
        # v2 integration destinations (user point I): an import-file profile
        # (method 3) or an ENABLED DB profile (method 4) may replace the
        # default output file. RPA (1) and web-form (2) need a human at the
        # screen, so they are never unattended destinations.
        handled = False
        if cfg.get("integration_db"):
            try:
                res = integrations_mod.db_write(cfg["integration_db"], values)
                if not res["dry_run"]:
                    destination = f"db:{cfg['integration_db'].get('table', '')} x{res['written']}"
                    handled = True
            except Exception as e:
                destination = f"db failed: {e}"
        if not handled and cfg.get("integration_file"):
            icfg = cfg["integration_file"]
            out_dir = cfg.get("integration_file_dir") or os.path.dirname(os.path.abspath(cfg["output_path"]))
            fname = integrations_mod.resolve_filename(icfg.get("filename_pattern") or "export_{date}.csv", profile.name)
            out_path = os.path.join(out_dir, fname)
            append = os.path.isfile(out_path)
            integrations_mod.export_import_file(values, [f.target_column for f in profile.fields], icfg, out_path, append=append)
            destination = out_path
            handled = True
        if not handled:
            append_output(rows, profile, cfg["output_path"])
            destination = cfg["output_path"]
        dest = _unique_dest(cfg["done_folder"], base)
        shutil.move(path, dest)
        decision = "accepted"
    else:
        dest = _unique_dest(cfg["review_folder"], base)
        shutil.move(path, dest)
        decision = "review"
    record = {"timestamp": _now(), "source_file": base, "moved_to": dest,
              "destination": destination,
              "profile": profile.name, "decision": decision,
              "threshold": threshold, "min_confidence": min_conf,
              "arithmetic_passed": arith["passed"], "arithmetic_checks": arith["checks"],
              "low_fields": [list(x) for x in low], "values": values,
              "confidences": confidences}
    write_audit(record, app_dir=app_dir)
    return {"decision": decision, "source": base, "moved_to": dest, "rows": rows,
            "values": values, "min_confidence": min_conf, "arithmetic": arith, "low": low}


def scan_watch_folder(folder):
    """New supported files in the watch folder (not recursive), sorted."""
    if not folder or not os.path.isdir(folder):
        return []
    out = []
    for fn in sorted(os.listdir(folder)):
        if fn.lower().endswith(SUPPORTED_EXTS):
            out.append(os.path.join(folder, fn))
    return out

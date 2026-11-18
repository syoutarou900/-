# -*- coding: utf-8 -*-
"""Built-in LOCAL VLM for ContextStruct — llama.cpp + Qwen2.5-VL-3B-Instruct GGUF.

Verified at build time (2026-11-12):
- llama.cpp release b10936, asset "llama-b10936-bin-win-cpu-x64.zip" = 18,426,326 bytes,
  downloaded from the official GitHub release in this build environment.
  Inside it (actual listing): llama-mtmd-cli.exe (90,112), mtmd.dll, llama.dll,
  llama-common.dll, ggml.dll, ggml-base.dll, ggml-cpu-*.dll, libomp.dll.
  Only those needed files are bundled under vlm_runtime/ next to app.py.
- Model repos (official ggml-org GGUF repos). v2: EXACT filenames and byte sizes
  were verified directly against the Hugging Face API model-tree endpoint
  (api/models/ggml-org/<repo>/tree/main) on 2026-11-12:
  3B repo ggml-org/Qwen2.5-VL-3B-Instruct-GGUF:
    Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf      = 1,929,901,056 bytes
    mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf =   844,757,728 bytes
    total = 2,774,658,784 bytes (approx. 2.8 GB)
  7B repo ggml-org/Qwen2.5-VL-7B-Instruct-GGUF (optional high-accuracy model):
    Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf      = 4,683,072,032 bytes
    mmproj-Qwen2.5-VL-7B-Instruct-Q8_0.gguf =   853,119,712 bytes
    total = 5,536,191,744 bytes (approx. 5.5 GB)
  Sizes are additionally confirmed at download time from Content-Length.
- After this one download, inference is fully offline and needs NO API key.
- Honest limit: on a CPU-only PC (no GPU) one page can take tens of seconds to
  a few minutes. The instant path is the rule engine; VLM is for images/scans.
- macOS: the bundled runtime above is a Windows build and cannot run on a Mac.
  On darwin the Windows .exe is never selected (see find_runtime_binary); the
  local VLM on Mac works only if the user manually places a macOS llama.cpp
  build (extensionless llama-mtmd-cli) into vlm_runtime/. The rule engine,
  OCR and every other feature work on Mac without it.
"""
import os, sys, re, json, subprocess, urllib.request, zipfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from context_core import get_app_dir, FieldResult, format_value, parse_number, parse_date

LLAMA_CPP_TAG = "b10936"
RUNTIME_ASSET = "llama-b10936-bin-win-cpu-x64.zip"
RUNTIME_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_CPP_TAG}/{RUNTIME_ASSET}"
RUNTIME_ZIP_SIZE = 18426326
RUNTIME_EXE_CANDIDATES = ["llama-mtmd-cli.exe", "llama-mtmd-cli", "llama-cli.exe", "llama-cli"]

MODEL_REPO = "ggml-org/Qwen2.5-VL-3B-Instruct-GGUF"
MODEL_FILE = "Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf"
MODEL_URL = f"https://huggingface.co/{MODEL_REPO}/resolve/main/{MODEL_FILE}"
MMPROJ_FILE = "mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf"
MMPROJ_URL = f"https://huggingface.co/{MODEL_REPO}/resolve/main/{MMPROJ_FILE}"
MODEL_FILES = [(MODEL_FILE, MODEL_URL), (MMPROJ_FILE, MMPROJ_URL)]
TOTAL_DOWNLOAD_GB_APPROX = 2.8
MIN_MODEL_BYTES = 500_000_000
MIN_MMPROJ_BYTES = 100_000_000

# --- v2 model registry: 3B (light) and 7B (high accuracy), both verified ---
MODEL7_REPO = "ggml-org/Qwen2.5-VL-7B-Instruct-GGUF"
MODEL7_FILE = "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"
MODEL7_URL = f"https://huggingface.co/{MODEL7_REPO}/resolve/main/{MODEL7_FILE}"
MMPROJ7_FILE = "mmproj-Qwen2.5-VL-7B-Instruct-Q8_0.gguf"
MMPROJ7_URL = f"https://huggingface.co/{MODEL7_REPO}/resolve/main/{MMPROJ7_FILE}"

MODELS = {
    "3b": {"repo": MODEL_REPO, "model_file": MODEL_FILE, "mmproj_file": MMPROJ_FILE,
           "model_url": MODEL_URL, "mmproj_url": MMPROJ_URL,
           "model_bytes": 1929901056, "mmproj_bytes": 844757728,
           "min_model_bytes": MIN_MODEL_BYTES, "min_mmproj_bytes": MIN_MMPROJ_BYTES,
           "approx_gb": 2.8},
    "7b": {"repo": MODEL7_REPO, "model_file": MODEL7_FILE, "mmproj_file": MMPROJ7_FILE,
           "model_url": MODEL7_URL, "mmproj_url": MMPROJ7_URL,
           "model_bytes": 4683072032, "mmproj_bytes": 853119712,
           "min_model_bytes": 1_000_000_000, "min_mmproj_bytes": MIN_MMPROJ_BYTES,
           "approx_gb": 5.5},
}

def model_spec(model_key="3b"):
    return MODELS.get(model_key or "3b", MODELS["3b"])

def selected_model_key(settings=None):
    try:
        if settings is None:
            from context_core import load_settings
            settings = load_settings()
        k = (settings or {}).get("vlm_model_size", "3b")
    except Exception:
        k = "3b"
    return k if k in MODELS else "3b"

def models_dir():
    d = os.path.join(get_app_dir(), "models"); os.makedirs(d, exist_ok=True); return d

def _resource_base():
    """Folder holding bundled resources shipped beside the app.

    When frozen by PyInstaller, modules no longer live next to vlm_runtime/,
    so resolve resources relative to the executable instead of __file__.
    In normal script runs this is exactly the script folder (unchanged).
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def bundled_runtime_dir():
    return os.path.join(_resource_base(), "vlm_runtime")

def downloaded_runtime_dir():
    return os.path.join(get_app_dir(), "vlm_runtime")

def find_runtime_binary(search_dirs=None):
    dirs = search_dirs or [bundled_runtime_dir(), downloaded_runtime_dir()]
    candidates = RUNTIME_EXE_CANDIDATES
    if sys.platform == "darwin":
        # The bundled/downloadable runtime in this package is a Windows build
        # (.exe + DLLs) that can never execute on macOS. On darwin only accept
        # extensionless binaries (e.g. a macOS llama.cpp build the user placed
        # in vlm_runtime/ manually), so a Windows .exe is never "found" here.
        candidates = [n for n in candidates if not n.lower().endswith(".exe")]
    for d in dirs:
        if not d or not os.path.isdir(d): continue
        for name in candidates:
            p = os.path.join(d, name)
            if os.path.isfile(p): return p
    return None

def bundled_models_dir():
    """A ./models folder shipped inside a distributor's full package (v2)."""
    return os.path.join(_resource_base(), "models")

def model_status(mdir=None, model_key="3b", min_model_bytes=None, min_mmproj_bytes=None):
    spec = model_spec(model_key)
    if min_model_bytes is None: min_model_bytes = spec["min_model_bytes"]
    if min_mmproj_bytes is None: min_mmproj_bytes = spec["min_mmproj_bytes"]
    if mdir is None:
        primary = _model_status_in(models_dir(), spec, model_key, min_model_bytes, min_mmproj_bytes)
        if primary["complete"]:
            return primary
        bundled = bundled_models_dir()
        if os.path.isdir(bundled):
            alt = _model_status_in(bundled, spec, model_key, min_model_bytes, min_mmproj_bytes)
            if alt["complete"]:
                return alt
        return primary
    return _model_status_in(mdir, spec, model_key, min_model_bytes, min_mmproj_bytes)

def _model_status_in(mdir, spec, model_key, min_model_bytes, min_mmproj_bytes):
    info = {"dir": mdir, "model_key": model_key, "files": {}, "missing": [], "complete": False}
    for fname, _url, minb in [(spec["model_file"], spec["model_url"], min_model_bytes), (spec["mmproj_file"], spec["mmproj_url"], min_mmproj_bytes)]:
        p = os.path.join(mdir, fname)
        exists = os.path.isfile(p)
        size = os.path.getsize(p) if exists else 0
        ok = exists and size >= minb
        info["files"][fname] = {"path": p, "exists": exists, "size": size, "ok": ok}
        if not ok: info["missing"].append(fname)
    info["complete"] = len(info["missing"]) == 0
    return info

def _few_shot_lines(few_shot):
    out = []
    if few_shot:
        out.append("Examples learned from this user's confirmed corrections (same profile). Follow them when the same pattern appears:")
        for ex in few_shot:
            try:
                out.append(f'- Field "{ex.get("field", "")}": a previous reading "{ex.get("original", "")}" was corrected to "{ex.get("corrected", "")}" (source snippet: {ex.get("source_snippet", "")})')
            except Exception:
                continue
    return out

def build_vlm_prompt(profile, variant=0, few_shot=None):
    """Image-understanding prompt: the model receives the IMAGE itself (not OCR text).
    It must read layout, table structure and spatial relations, map values to profile
    fields by their headings, return line items row by row, interpret imperfect scans
    as far as they are readable, and never guess.
    variant=1 is a second phrasing used for self-consistency double-reading (v2).
    few_shot: recent confirmed corrections injected as examples (v2 learning)."""
    lines = []
    if variant == 1:
        lines.append("Examine the document image carefully, as a human clerk would. The input is the IMAGE of the document itself (not OCR text).")
        lines.append("Use the visual layout: the table structure (rows and columns), the spatial layout and the position of each heading relative to its value, ruled lines / boxed cells, and grouping on the page.")
        lines.append("Assign each value to exactly one profile field below, chosen by the heading printed next to / above it in the image.")
        lines.append('Answer with ONLY this JSON shape: {"fields": {<target column>: <value>, ...}, "items": [{<target column>: <value>, ...}, ...]} — "fields" = document-level values, "items" = one object per line-item row ([] when there is no table).')
        lines.append("Missing or unreadable values must be \"\". Do NOT guess and do NOT invent values you cannot actually read.")
        lines.append("The page may be tilted or stained (dirty FAX), and may contain handwritten notes and stamps/seals. Read handwriting where it is legible, interpret stamps and stains as far as genuinely readable, and leave the rest empty.")
    else:
        lines.append("You are a document image-understanding engine. You are given the IMAGE of a document itself (not OCR text).")
        lines.append("Read the image using its visual layout: the table structure (rows and columns), the spatial layout and positions of headings and values, ruled lines / boxed cells, and which heading each number belongs to.")
        lines.append("Map every value to the profile fields below, matching by the heading printed next to / above the value in the image.")
        lines.append('Return ONLY a JSON object in exactly this shape: {"fields": {<target column>: <value>, ...}, "items": [{<target column>: <value>, ...}, ...]}')
        lines.append('"fields" holds document-level values (one per document). "items" holds one object per line-item row of any table in the image (same columns); use an empty list [] if there is no table of line items.')
        lines.append("If a value is not present or not readable, use an empty string \"\". Do NOT guess, do NOT invent, and do NOT fill a field with a plausible value you cannot actually read in the image.")
        lines.append("The scan may be tilted, dirty (FAX noise), or contain handwritten notes and stamps/seals: interpret them as far as they are genuinely readable, and leave unreadable fields empty rather than guessing. Read handwriting where it is legible; do not invent handwriting you cannot read.")
    lines.append("Fields (target column | display name | type | hint keywords):")
    has_wholesale = any("卸値" in f.target_column or "wholesale" in f.target_column.lower() for f in profile.fields)
    has_retail = any("売価" in f.target_column or "retail" in f.target_column.lower() for f in profile.fields)
    for f in profile.fields:
        lines.append(f'- "{f.target_column}": {f.display_name} (type: {f.field_type}; keywords: {f.keywords})')
    if has_wholesale and has_retail:
        lines.append("IMPORTANT: 卸値 (wholesale price / purchase price) and 売価 (retail / selling price) are DIFFERENT fields, distinguished by their headings in the layout. Do not swap them and do not copy one value into the other.")
    lines.extend(_few_shot_lines(few_shot))
    lines.append("For dates, output YYYY-MM-DD. For numbers and amounts, output digits only (no commas, no currency symbols, no units).")
    return chr(10).join(lines)

def build_field_prompt(profile, target_column):
    """Verification pass (v2): a field-specific re-read question for ONE field whose
    engines disagreed or whose arithmetic check failed."""
    fdef = next((f for f in profile.fields if f.target_column == target_column), None)
    lines = []
    lines.append("You are re-checking ONE field of a document image because automated readers disagreed about it.")
    lines.append("Look at the IMAGE itself (not OCR text): use the visual layout, the table structure (rows and columns), the position of the heading relative to the value, and ruled lines / boxed cells.")
    if fdef is not None:
        lines.append(f'Find ONLY this field: "{fdef.target_column}" — display name: {fdef.display_name}, type: {fdef.field_type}, hint keywords: {fdef.keywords}.')
    else:
        lines.append(f'Find ONLY this field: "{target_column}".')
    lines.append("Read handwriting where it is legible. If the value is absent or not readable, answer with an empty string. Do NOT guess.")
    lines.append(f'Return ONLY a JSON object like {{"{target_column}": "<value>"}} with no other text.')
    lines.append("For dates, output YYYY-MM-DD. For numbers and amounts, output digits only.")
    return chr(10).join(lines)

def parse_vlm_json(text):
    """Tolerant JSON parser: handles ```json fences and surrounding prose."""
    if not text: return {}
    s = str(text)
    s = re.sub(r"```(?:json)?", "", s)
    start = s.find("{"); end = s.rfind("}")
    if start < 0 or end <= start: return {}
    blob = s[start:end + 1]
    try:
        return json.loads(blob)
    except Exception:
        pass
    blob2 = re.sub(r",\s*([}\]])", r"\1", blob)
    try:
        return json.loads(blob2)
    except Exception:
        return {}

def _row_from_dict(item, profile):
    row = {}
    for f in profile.fields:
        raw = item.get(f.target_column, "")
        if raw is None: raw = ""
        raw = str(raw).strip()
        if not raw:
            row[f.target_column] = FieldResult("", 0, "VLM: not_found", "")
            continue
        if f.field_type in ("number", "amount"):
            v = parse_number(raw)
            if v: row[f.target_column] = FieldResult(v, 85, "VLM + reason_type_ok", raw)
            else: row[f.target_column] = FieldResult(raw, 50, "VLM: type_check_failed", raw)
        elif f.field_type == "date":
            v = parse_date(raw)
            if v: row[f.target_column] = FieldResult(v, 85, "VLM + reason_type_ok", raw)
            else: row[f.target_column] = FieldResult(raw, 50, "VLM: type_check_failed", raw)
        else:
            row[f.target_column] = FieldResult(raw, 80, "VLM", raw)
    return row

def vlm_data_to_rows(data, profile):
    """Convert parsed VLM JSON into preview rows with confidence.
    Accepts: {"fields": {...}, "items": [{...}, ...]} (line items row by row, document
    fields fill every row), a plain {column: value} dict, or a list of dicts."""
    if isinstance(data, list):
        return [_row_from_dict(it or {}, profile) for it in data] or [_row_from_dict({}, profile)]
    data = data or {}
    doc = data.get("fields") if isinstance(data.get("fields"), dict) else {k: v for k, v in data.items() if k != "items"}
    items = data.get("items") if isinstance(data.get("items"), list) else []
    if items:
        rows = []
        for it in items:
            merged = dict(doc); merged.update(it or {})
            rows.append(_row_from_dict(merged, profile))
        return rows
    return [_row_from_dict(doc, profile)]

# --- Image pipeline: the VLM always receives an IMAGE, never OCR text ---
def render_pdf_page_image(pdf_path, page_index=0, dpi=300, out_path=None):
    """Render one PDF page to a high-resolution PNG so the VLM can understand the
    scanned page as an image (layout, ruled lines, stamps), not as extracted text."""
    import fitz
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    pix = page.get_pixmap(dpi=int(dpi))
    if out_path is None:
        import tempfile
        out_path = os.path.join(tempfile.gettempdir(), f"contextstruct_vlm_page{page_index}.png")
    pix.save(out_path); doc.close()
    return out_path

def prepare_vlm_image(source_path, dpi=300):
    """Return an image file path to feed the VLM, whatever the source was:
    image file -> itself; PDF -> high-res rendered page image; else None."""
    if not source_path: return None
    ext = os.path.splitext(source_path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"):
        return source_path
    if ext == ".pdf":
        return render_pdf_page_image(source_path, 0, dpi=dpi)
    return None

def _download_file(url, dest, progress_cb=None):
    req = urllib.request.Request(url, headers={"User-Agent": "ContextStruct/1.0"})
    tmp = dest + ".part"
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(tmp, "wb") as out:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk: break
                out.write(chunk); done += len(chunk)
                if progress_cb: progress_cb(done, total)
    os.replace(tmp, dest)
    return dest

def download_models(progress_cb=None, mdir=None, model_key="3b"):
    """Download model + mmproj for the chosen model (3B approx 2.8 GB / 7B approx
    5.5 GB total) with per-file progress (done,total,filename). Exact sizes are
    verified filenames above and are confirmed again from Content-Length."""
    spec = model_spec(model_key)
    files = [(spec["model_file"], spec["model_url"]), (spec["mmproj_file"], spec["mmproj_url"])]
    mdir = mdir or models_dir(); os.makedirs(mdir, exist_ok=True)
    st = model_status(mdir, model_key=model_key)
    for fname, url in files:
        if st["files"][fname]["ok"]: continue
        dest = os.path.join(mdir, fname)
        def cb(done, total, _f=fname):
            if progress_cb: progress_cb(done, total, _f)
        _download_file(url, dest, cb)
    return model_status(mdir, model_key=model_key)

def download_runtime(progress_cb=None):
    """Fallback: if the bundled vlm_runtime is missing, download the pinned llama.cpp zip and extract the needed files."""
    if sys.platform == "darwin":
        # The pinned fallback asset is the Windows x64 build; downloading it
        # on macOS would fetch ~18 MB that can never run there. On Mac the
        # local VLM needs a macOS llama.cpp build placed in vlm_runtime/
        # manually (see README, Mac chapter). Returning None makes the
        # caller report the runtime as missing, which is the honest state.
        return None
    dest_dir = downloaded_runtime_dir(); os.makedirs(dest_dir, exist_ok=True)
    zpath = os.path.join(dest_dir, RUNTIME_ASSET)
    _download_file(RUNTIME_URL, zpath, lambda d, t: progress_cb(d, t, RUNTIME_ASSET) if progress_cb else None)
    keep_prefix = ("ggml-cpu-",)
    keep = {"llama-mtmd-cli.exe", "mtmd.dll", "llama.dll", "llama-common.dll", "ggml.dll", "ggml-base.dll", "libomp.dll"}
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            if info.filename in keep or info.filename.startswith(keep_prefix):
                z.extract(info, dest_dir)
    try: os.remove(zpath)
    except Exception: pass
    return find_runtime_binary()

# ------------------------------------------------------------- GPU support ----
# GPU asset names/sizes VERIFIED against the official llama.cpp b10936 release
# asset list (GitHub API) on 2026-11-12:
#   llama-b10936-bin-win-vulkan-x64.zip    =  31,673,236 bytes
#   llama-b10936-bin-win-cuda-12.4-x64.zip = 254,065,100 bytes
#   cudart-llama-bin-win-cuda-12.4-x64.zip = 391,443,627 bytes (CUDA runtime DLLs,
#                                            required next to the CUDA build)
GPU_ASSETS = {
    "vulkan": [{"name": "llama-b10936-bin-win-vulkan-x64.zip", "size": 31673236}],
    "cuda": [{"name": "llama-b10936-bin-win-cuda-12.4-x64.zip", "size": 254065100},
             {"name": "cudart-llama-bin-win-cuda-12.4-x64.zip", "size": 391443627}],
}
GPU_BASE_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_CPP_TAG}/"

def detect_gpu(which=None, run=None, env=None, platform=None):
    """Simple GPU detection. On Windows: NVIDIA via nvidia-smi presence+run,
    generic GPU via the Vulkan loader (vulkan-1.dll in System32) or vulkaninfo.
    Elsewhere / on any error it degrades to 'unknown -> CPU'.
    which/run/env/platform are injectable for unit tests."""
    which = which or shutil.which
    env = env or os.environ
    platform = platform or sys.platform
    is_win = str(platform).startswith("win")
    result = {"is_windows": is_win, "nvidia": False, "vulkan": False, "recommended": "cpu"}
    # NVIDIA
    try:
        smi = which("nvidia-smi") or which("nvidia-smi.exe")
        if smi:
            if run is None:
                result["nvidia"] = True  # presence alone is a strong signal
            else:
                try:
                    rc = run([smi, "-L"])
                    result["nvidia"] = (rc == 0)
                except Exception:
                    result["nvidia"] = False
    except Exception:
        pass
    # Vulkan (generic GPU)
    try:
        if is_win:
            windir = env.get("windir") or env.get("SystemRoot") or r"C:\Windows"
            if os.path.isfile(os.path.join(windir, "System32", "vulkan-1.dll")):
                result["vulkan"] = True
        if not result["vulkan"] and which("vulkaninfo"):
            result["vulkan"] = True
    except Exception:
        pass
    if result["nvidia"]:
        result["recommended"] = "cuda"
    elif result["vulkan"]:
        result["recommended"] = "vulkan"
    return result

def _gpu_roots():
    here = _resource_base()
    return [os.path.join(here, "vlm_runtime_gpu"), os.path.join(get_app_dir(), "vlm_runtime_gpu")]

def find_gpu_runtime_binary(flavor=None):
    """Search bundled/downloaded GPU runtimes. Returns (path, flavor) or None."""
    flavors = [flavor] if flavor else ["cuda", "vulkan"]
    for root in _gpu_roots():
        for fl in flavors:
            d = os.path.join(root, fl)
            if not os.path.isdir(d):
                continue
            for name in RUNTIME_EXE_CANDIDATES:
                p = os.path.join(d, name)
                if os.path.isfile(p):
                    return (p, fl)
    return None

def download_gpu_runtime(flavor, progress_cb=None):
    """Download+extract the official GPU runtime (Vulkan ~32MB / CUDA ~645MB
    including the cudart package) into <app data>/vlm_runtime_gpu/<flavor>/."""
    if sys.platform == "darwin":
        # The pinned GPU assets are Windows builds (Vulkan/CUDA for Windows
        # x64); they cannot run on macOS. Refuse honestly instead of
        # downloading hundreds of MB that would never execute.
        raise RuntimeError("GPU runtime downloads are Windows-only in this package; on macOS the local VLM uses a manually placed macOS llama.cpp build (CPU/Metal) — see the README Mac chapter.")
    if flavor not in GPU_ASSETS:
        raise ValueError(f"unknown GPU flavor: {flavor}")
    dest_dir = os.path.join(get_app_dir(), "vlm_runtime_gpu", flavor)
    os.makedirs(dest_dir, exist_ok=True)
    for asset in GPU_ASSETS[flavor]:
        zpath = os.path.join(dest_dir, asset["name"])
        _download_file(GPU_BASE_URL + asset["name"], zpath,
                       lambda d, t, _f=asset["name"]: progress_cb(d, t, _f) if progress_cb else None)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(dest_dir)
        try:
            os.remove(zpath)
        except Exception:
            pass
    found = find_gpu_runtime_binary(flavor)
    return found[0] if found else None

def best_runtime():
    """(binary, mode) — a downloaded GPU runtime wins over the bundled CPU one.
    mode is 'gpu_cuda' / 'gpu_vulkan' / 'cpu' / 'none'."""
    gpu = find_gpu_runtime_binary()
    if gpu:
        return gpu[0], "gpu_" + gpu[1]
    cpu = find_runtime_binary()
    if cpu:
        return cpu, "cpu"
    return None, "none"

def effective_mode():
    _b, mode = best_runtime()
    return {"gpu_cuda": "GPU (CUDA)", "gpu_vulkan": "GPU (Vulkan)", "cpu": "CPU"}.get(mode, "CPU")

def _run_llama(image_path, prompt, model_key="3b", timeout=1800):
    """Run the llama.cpp multimodal CLI once and return raw stdout.
    Uses a GPU runtime with -ngl offload when one was downloaded; if the GPU
    launch fails, it automatically falls back to the bundled CPU runtime."""
    spec = model_spec(model_key)
    st = model_status(model_key=model_key)
    if not st["complete"]:
        raise FileNotFoundError("VLM model not downloaded: " + ", ".join(st["missing"]))
    binary, mode = best_runtime()
    if not binary:
        binary = download_runtime()
        mode = "cpu"
    if not binary:
        raise FileNotFoundError("llama.cpp runtime (llama-mtmd-cli) not found")
    def _once(binpath, ngl):
        cmd = [binpath, "-m", os.path.join(st["dir"], spec["model_file"]), "--mmproj", os.path.join(st["dir"], spec["mmproj_file"]),
               "--image", image_path, "-p", prompt, "-n", "1024", "--temp", "0.1"]
        if ngl:
            cmd += ["-ngl", "999"]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=timeout)
        return proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")
    if mode.startswith("gpu"):
        out = ""
        try:
            rc, out = _once(binary, True)
            if rc == 0:
                return out
        except Exception:
            pass
        cpu = find_runtime_binary()
        if cpu and cpu != binary:
            _rc, out = _once(cpu, False)
            return out
        return out
    _rc, out = _once(binary, False)
    return out

def run_local_vlm(image_path, profile, runner=None, timeout=1800, model_key=None, prompt_variant=0, few_shot=None):
    """Return preview rows. runner(prompt, image_path)->raw text is injectable for tests/mocks.
    Real path: llama-mtmd-cli -m model --mmproj mmproj --image image -p prompt.
    v2: model_key selects 3B/7B (default: the user's setting); prompt_variant picks
    the self-consistency phrasing; few_shot injects recent confirmed corrections."""
    prompt = build_vlm_prompt(profile, variant=prompt_variant, few_shot=few_shot)
    if runner is not None:
        raw = runner(prompt, image_path)
        return vlm_data_to_rows(parse_vlm_json(raw), profile)
    key = model_key or selected_model_key()
    raw = _run_llama(image_path, prompt, model_key=key, timeout=timeout)
    return vlm_data_to_rows(parse_vlm_json(raw), profile)

def run_field_reread(image_path, profile, target_column, runner=None, timeout=1800, model_key=None):
    """Verification pass: re-read ONE disputed field from the image with a
    field-specific question. Returns a FieldResult or None when unreadable.
    runner(prompt, image_path)->raw text is injectable for tests/mocks."""
    prompt = build_field_prompt(profile, target_column)
    if runner is not None:
        raw = runner(prompt, image_path)
    else:
        raw = _run_llama(image_path, prompt, model_key=model_key or selected_model_key(), timeout=timeout)
    data = parse_vlm_json(raw)
    val = None
    if isinstance(data, dict):
        if target_column in data:
            val = data.get(target_column)
        elif isinstance(data.get("fields"), dict):
            val = data["fields"].get(target_column)
        elif isinstance(data.get("items"), list) and data["items"]:
            val = (data["items"][0] or {}).get(target_column)
    if val is None or str(val).strip() == "":
        return None
    fdef = next((f for f in profile.fields if f.target_column == target_column), None)
    ftype = fdef.field_type if fdef else "text"
    raw_s = str(val).strip()
    if ftype in ("number", "amount"):
        v = parse_number(raw_s)
        return FieldResult(v, 88, "verify_reread + reason_type_ok", raw_s) if v else FieldResult(raw_s, 55, "verify_reread: type_check_failed", raw_s)
    if ftype == "date":
        v = parse_date(raw_s)
        return FieldResult(v, 88, "verify_reread + reason_type_ok", raw_s) if v else FieldResult(raw_s, 55, "verify_reread: type_check_failed", raw_s)
    return FieldResult(raw_s, 85, "verify_reread", raw_s)

# -*- coding: utf-8 -*-
"""Image preprocessing for ContextStruct v2 — maximize OCR/VLM accuracy on
scanned paper, FAX and photographed documents.

Pipeline (OpenCV when available, Pillow fallback otherwise):
  1. upscale x2 (small scans become readable)
  2. deskew (estimate skew angle from dark-pixel geometry, rotate back)
  3. denoise
  4. CLAHE contrast enhancement  -> 'enhanced' variant
  5. adaptive binarization       -> 'binarized' variant

`preprocess_image()` returns {variant_name: PIL.Image} with keys
'original', 'enhanced', 'binarized'. `preprocess_to_files()` saves the
variants as temporary PNGs so they can be fed to OCR engines and to the
local VLM (which always receives an image, never text).

All functions are unit-testable without any OCR binary: they operate on
PIL images only.
"""
import os, math, tempfile

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except Exception:  # pragma: no cover - exercised only on cv2-less installs
    cv2 = None
    np = None
    HAS_CV2 = False

from PIL import Image, ImageOps, ImageEnhance, ImageFilter

MAX_SKEW_SEARCH = 15.0  # degrees; beyond this it is not a scan skew but a photo


# ---------------------------------------------------------------- skew ----
def estimate_skew(pil_image):
    """Estimate the skew angle (degrees) of the text lines in an image.
    Positive angle means the image is rotated counter-clockwise by that much.
    Returns 0.0 when no reliable estimate exists."""
    if pil_image is None:
        return 0.0
    if HAS_CV2:
        try:
            return _estimate_skew_cv2(pil_image)
        except Exception:
            pass
    try:
        return _estimate_skew_projection(pil_image)
    except Exception:
        return 0.0


def _estimate_skew_cv2(pil_image):
    img = pil_image.convert("L")
    # downscale for speed
    w, h = img.size
    scale = 1000.0 / max(w, h) if max(w, h) > 1000 else 1.0
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    arr = np.array(img)
    _, bw = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(bw > 0))
    if len(coords) < 100:
        return 0.0
    rect = cv2.minAreaRect(coords[:, ::-1].astype(np.float32))
    angle = float(rect[-1])
    # minAreaRect angle conventions differ by version; normalize to (-45, 45]
    if angle < -45:
        angle += 90.0
    if angle > 45:
        angle -= 90.0
    # coords were (row, col); minAreaRect on (x=col, y=row) flips the sign
    angle = -angle
    if abs(angle) < 0.05 or abs(angle) > MAX_SKEW_SEARCH:
        return 0.0 if abs(angle) < 0.05 else angle
    return angle


def _estimate_skew_projection(pil_image):
    """Fallback: projection-profile search over small angles (Pillow/numpy-free
    implementation using PIL rotations on a downscaled binary image)."""
    img = pil_image.convert("L")
    w, h = img.size
    scale = 500.0 / max(w, h) if max(w, h) > 500 else 1.0
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    bw = img.point(lambda p: 0 if p < 128 else 255)
    best_angle, best_score = 0.0, -1.0
    a = -5.0
    while a <= 5.0:
        rot = bw.rotate(a, resample=Image.BILINEAR, fillcolor=255)
        px = rot.load()
        rw, rh = rot.size
        score = 0.0
        prev = None
        for y in range(rh):
            row_dark = sum(1 for x in range(0, rw, 3) if px[x, y] == 0)
            if prev is not None:
                score += abs(row_dark - prev)
            prev = row_dark
        if score > best_score:
            best_score, best_angle = score, a
        a += 0.5
    return -best_angle


def deskew_image(pil_image):
    """Return a deskewed copy. Uses the estimated skew; no-op when ~0."""
    angle = estimate_skew(pil_image)
    if abs(angle) < 0.1:
        return pil_image.copy()
    # estimate_skew reports the content's own rotation (PIL convention);
    # undoing it needs the opposite rotation in both backends (verified
    # empirically on synthetic rotated patterns).
    if HAS_CV2:
        arr = np.array(pil_image.convert("RGB"))
        h, w = arr.shape[:2]
        center = (w // 2, h // 2)
        m = cv2.getRotationMatrix2D(center, -angle, 1.0)
        out = cv2.warpAffine(arr, m, (w, h), flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
        return Image.fromarray(out)
    return pil_image.rotate(-angle, resample=Image.BICUBIC, expand=False, fillcolor=(255, 255, 255))


# ------------------------------------------------------------- variants ----
def _to_gray_array(pil_image):
    return np.array(pil_image.convert("L"))


def enhance_image(pil_image):
    """Denoise + CLAHE contrast enhancement (grayscale, kept as RGB for VLM)."""
    if HAS_CV2:
        gray = _to_gray_array(pil_image)
        den = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        out = clahe.apply(den)
        return Image.fromarray(out).convert("RGB")
    img = pil_image.convert("L").filter(ImageFilter.MedianFilter(size=3))
    img = ImageOps.autocontrast(img, cutoff=1)
    img = ImageEnhance.Contrast(img).enhance(1.4)
    return img.convert("RGB")


def binarize_image(pil_image):
    """Adaptive binarization: black text on white, tolerant of uneven FAX light."""
    if HAS_CV2:
        gray = _to_gray_array(pil_image)
        den = cv2.GaussianBlur(gray, (3, 3), 0)
        out = cv2.adaptiveThreshold(den, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY, 31, 12)
        return Image.fromarray(out).convert("RGB")
    img = pil_image.convert("L")
    # simple global fallback: Otsu via histogram midpoint of bimodal peaks
    hist = img.histogram()
    total = sum(hist)
    sum_all = sum(i * h for i, h in enumerate(hist))
    w_b = sum_b = 0
    max_var, thresh = -1, 128
    for i, h in enumerate(hist):
        w_b += h
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * h
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > max_var:
            max_var, thresh = var, i
    return img.point(lambda p: 255 if p > thresh else 0).convert("RGB")


def upscale_image(pil_image, factor=2):
    w, h = pil_image.size
    resample = Image.LANCZOS
    if HAS_CV2:
        arr = np.array(pil_image.convert("RGB"))
        out = cv2.resize(arr, (w * factor, h * factor), interpolation=cv2.INTER_CUBIC)
        return Image.fromarray(out)
    return pil_image.resize((w * factor, h * factor), resample)


def preprocess_image(pil_image, upscale=True):
    """Full pipeline. Returns {'original': deskewed-upscaled, 'enhanced': ...,
    'binarized': ...} as PIL images (RGB)."""
    img = pil_image.convert("RGB")
    base = deskew_image(img)
    if upscale:
        base = upscale_image(base, 2)
    return {
        "original": base,
        "enhanced": enhance_image(base),
        "binarized": binarize_image(base),
    }


def preprocess_to_files(source_path, out_dir=None, upscale=True):
    """Load an image file, preprocess, save variants as PNGs, return
    {variant: path}. Used to feed extra OCR/VLM voters."""
    img = Image.open(source_path)
    variants = preprocess_image(img, upscale=upscale)
    out_dir = out_dir or tempfile.mkdtemp(prefix="contextstruct_pre_")
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(source_path))[0]
    paths = {}
    for name, im in variants.items():
        p = os.path.join(out_dir, f"{base}_{name}.png")
        im.save(p)
        paths[name] = p
    return paths

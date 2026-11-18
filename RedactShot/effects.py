# -*- coding: utf-8 -*-
"""Image effects (pixelate / blur / blackout) built on Pillow.

GUI-independent. No display name is hard-coded here.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter

EFFECTS = ["pixelate", "blur", "blackout"]

# Blur is FIXED at this strength by design (user decision, 2026-11-15):
# at low strengths blurred text could still be read back, so the blur
# effect always uses this level and ignores any strength passed in.
# The level is the maximum of the UI strength scale (radius 15 px) and
# was verified by re-OCR: 0 of the planted secrets remained readable.
BLUR_FIXED_STRENGTH = 10
BLUR_FIXED_RADIUS = BLUR_FIXED_STRENGTH * 1.5

# Pixelate (mosaic) is likewise FIXED (2026-11-15 design refresh: the
# strength slider was removed from the UI entirely, so no effect can be
# weakened by the user). The fixed level equals the former UI default
# strength 6 (block 14 px). It was chosen by re-OCR verification
# (quality/verify_pixelate_levels.py, flows A/B/C incl. a small-text
# image at 14/20 px): 0 of 24 planted secrets remained readable.
PIXELATE_FIXED_STRENGTH = 6
PIXELATE_FIXED_BLOCK = 2 + PIXELATE_FIXED_STRENGTH * 2


def _clip_region(x, y, w, h, img_w, img_h):
    x1 = max(0, int(x))
    y1 = max(0, int(y))
    x2 = min(img_w, int(x) + int(w))
    y2 = min(img_h, int(y) + int(h))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def apply_effects(pil_image, items):
    """Return a NEW PIL Image with the effects applied.

    The input image is never modified.
    items: iterable of (x, y, w, h, effect, strength) tuples.
    The strength element is accepted for call compatibility but is
    IGNORED for every effect: blur always uses BLUR_FIXED_STRENGTH and
    pixelate always uses PIXELATE_FIXED_STRENGTH, so neither can ever
    be weakened; blackout never used it. Regions are clipped to the
    image bounds.
    """
    result = pil_image.copy()
    if not items:
        return result

    img_w, img_h = result.size

    for item in items:
        if item is None:
            continue
        x, y, w, h, effect, strength = item
        if effect not in EFFECTS:
            raise ValueError(f"unknown effect: {effect!r}")
        try:
            strength = int(strength)
        except Exception:
            strength = 1
        strength = max(1, min(10, strength))

        region = _clip_region(x, y, w, h, img_w, img_h)
        if region is None:
            continue
        x1, y1, x2, y2 = region
        rw = x2 - x1
        rh = y2 - y1

        if effect == "blackout":
            draw = ImageDraw.Draw(result)
            if result.mode == "RGBA":
                fill = (0, 0, 0, 255)
            elif result.mode in ("LA", "PA"):
                fill = (0, 255)
            elif result.mode == "L":
                fill = 0
            else:
                fill = (0, 0, 0)
            draw.rectangle([x1, y1, x2 - 1, y2 - 1], fill=fill)

        elif effect == "pixelate":
            # Fixed safe level: the requested strength is deliberately
            # not honoured (see PIXELATE_FIXED_STRENGTH above).
            block = PIXELATE_FIXED_BLOCK
            crop = result.crop((x1, y1, x2, y2))
            small_w = max(1, rw // block)
            small_h = max(1, rh // block)
            small = crop.resize((small_w, small_h), Image.NEAREST)
            pixelated = small.resize((rw, rh), Image.NEAREST)
            result.paste(pixelated, (x1, y1))

        elif effect == "blur":
            # Fixed safe level: the requested strength is deliberately
            # not honoured for blur (see BLUR_FIXED_STRENGTH above).
            radius = BLUR_FIXED_RADIUS
            crop = result.crop((x1, y1, x2, y2))
            blurred = crop.filter(ImageFilter.GaussianBlur(radius=radius))
            result.paste(blurred, (x1, y1))

    return result

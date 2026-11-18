# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from PIL import Image

import effects


def patterned_image(w=100, h=100):
    """Deterministic high-detail image (1px checkerboard + gradient)."""
    img = Image.new("RGB", (w, h))
    px = img.load()
    for yy in range(h):
        for xx in range(w):
            if (xx + yy) % 2 == 0:
                px[xx, yy] = (255, 255, 255)
            else:
                px[xx, yy] = (0, 0, 0)
    return img


def region_pixels(img, x, y, w, h):
    return [img.getpixel((xx, yy)) for yy in range(y, y + h) for xx in range(x, x + w)]


def test_effects_list():
    assert effects.EFFECTS == ["pixelate", "blur", "blackout"]


@pytest.mark.parametrize("effect", effects.EFFECTS)
def test_effect_changes_region_pixels(effect):
    img = patterned_image()
    before = region_pixels(img, 10, 10, 40, 40)
    out = effects.apply_effects(img, [(10, 10, 40, 40, effect, 5)])
    after = region_pixels(out, 10, 10, 40, 40)
    assert after != before


@pytest.mark.parametrize("effect", effects.EFFECTS)
def test_original_image_unchanged(effect):
    img = patterned_image()
    snapshot = img.copy()
    out = effects.apply_effects(img, [(10, 10, 40, 40, effect, 5)])
    assert out is not img
    assert list(img.getdata()) == list(snapshot.getdata())


@pytest.mark.parametrize("effect", effects.EFFECTS)
def test_outside_region_unchanged(effect):
    img = patterned_image()
    out = effects.apply_effects(img, [(10, 10, 40, 40, effect, 5)])
    # Corners / areas outside the target region keep their pixels.
    for pt in [(0, 0), (99, 0), (0, 99), (99, 99), (9, 10), (50, 10), (10, 50)]:
        assert out.getpixel(pt) == img.getpixel(pt)


def test_blackout_fills_black():
    img = patterned_image()
    out = effects.apply_effects(img, [(10, 10, 40, 40, "blackout", 3)])
    assert set(region_pixels(out, 10, 10, 40, 40)) == {(0, 0, 0)}


def test_pixelate_makes_uniform_blocks():
    img = patterned_image()
    out = effects.apply_effects(img, [(0, 0, 40, 40, "pixelate", 5)])
    # With the fixed block size (14), pixels inside one block share a colour.
    block_pixels = {out.getpixel((xx, yy)) for yy in range(0, 11) for xx in range(0, 11)}
    assert len(block_pixels) == 1


def test_blur_reduces_checkerboard_contrast():
    img = patterned_image()
    out = effects.apply_effects(img, [(10, 10, 40, 40, "blur", 5)])
    vals = {out.getpixel((xx, yy)) for yy in range(20, 30) for xx in range(20, 30)}
    # Blurred interior is no longer pure black / pure white only.
    assert any(v not in ((0, 0, 0), (255, 255, 255)) for v in vals)


def test_region_clipped_to_image_bounds():
    img = patterned_image(50, 50)
    out = effects.apply_effects(img, [(-20, -20, 60, 60, "blackout", 5)])
    assert out.size == (50, 50)
    assert out.getpixel((0, 0)) == (0, 0, 0)
    assert out.getpixel((39, 39)) == (0, 0, 0)
    # Outside the (clipped) region stays untouched.
    assert out.getpixel((49, 49)) == img.getpixel((49, 49))


def test_empty_items_returns_equal_copy():
    img = patterned_image()
    out = effects.apply_effects(img, [])
    assert out is not img
    assert list(out.getdata()) == list(img.getdata())


def test_blur_strength_is_fixed():
    # Blur ignores the requested strength entirely: the weakest and the
    # strongest request must produce byte-identical output, so blur can
    # never be weakened below the fixed safe level.
    img = patterned_image()
    weak = effects.apply_effects(img, [(10, 10, 40, 40, "blur", 1)])
    mid = effects.apply_effects(img, [(10, 10, 40, 40, "blur", 5)])
    strong = effects.apply_effects(img, [(10, 10, 40, 40, "blur", 10)])
    assert list(weak.getdata()) == list(mid.getdata()) == list(strong.getdata())


def test_blur_fixed_level_fully_averages_detail():
    # At the fixed level (radius = BLUR_FIXED_RADIUS), a 1px checkerboard
    # in the interior of the region must be averaged to near-uniform
    # mid-grey: no black/white detail survives that OCR could read.
    assert effects.BLUR_FIXED_STRENGTH >= 5  # at/above the old "recommended" level
    img = patterned_image()
    out = effects.apply_effects(img, [(10, 10, 60, 60, "blur", 1)])
    vals = [out.getpixel((xx, yy)) for yy in range(35, 55) for xx in range(35, 55)]
    for v in vals:
        assert all(100 <= ch <= 155 for ch in v), v


def test_pixelate_strength_is_fixed():
    # Pixelate ignores the requested strength entirely (same design as
    # blur): the weakest and the strongest request must produce
    # byte-identical output, so pixelate can never be weakened below
    # the fixed safe level.
    img = Image.new("RGB", (100, 100))
    px = img.load()
    for yy in range(100):
        for xx in range(100):
            px[xx, yy] = ((xx * 2) % 256, (yy * 2) % 256, (xx + yy) % 256)
    weak = effects.apply_effects(img, [(0, 0, 60, 60, "pixelate", 1)])
    mid = effects.apply_effects(img, [(0, 0, 60, 60, "pixelate", 6)])
    strong = effects.apply_effects(img, [(0, 0, 60, 60, "pixelate", 10)])
    assert list(weak.getdata()) == list(mid.getdata()) == list(strong.getdata())


def test_pixelate_fixed_level_block_size():
    # The fixed level is the former default strength 6 (block 14 px),
    # verified by re-OCR to leave 0 of 24 planted secrets readable.
    assert effects.PIXELATE_FIXED_STRENGTH == 6
    assert effects.PIXELATE_FIXED_BLOCK == 14
    img = patterned_image()
    out = effects.apply_effects(img, [(0, 0, 56, 56, "pixelate", 1)])
    # Each 14x14 block is a single flat colour.
    for by in (0, 14, 28):
        for bx in (0, 14, 28):
            block_pixels = {out.getpixel((xx, yy))
                            for yy in range(by, by + 13) for xx in range(bx, bx + 13)}
            assert len(block_pixels) == 1


def test_multiple_items_applied():
    img = patterned_image()
    out = effects.apply_effects(img, [
        (0, 0, 20, 20, "blackout", 5),
        (80, 80, 20, 20, "blackout", 5),
    ])
    assert out.getpixel((5, 5)) == (0, 0, 0)
    assert out.getpixel((85, 85)) == (0, 0, 0)
    assert out.getpixel((50, 50)) == img.getpixel((50, 50))

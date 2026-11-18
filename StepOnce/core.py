# -*- coding: utf-8 -*-
"""Core logic for StepOnce: project model, project
save/load (folder + ZIP), mosaic/marker image rendering, draft-sentence
generation, and the optional DeepL translation client.

No Qt imports here (except none at all) so everything is unit-testable.
Coordinates for clicks and mosaic rectangles are stored as relative
fractions (0..1) of the image size, so they survive resolution changes.
"""

import json
import os
import shutil
import urllib.request
import urllib.parse
import zipfile
from dataclasses import dataclass, field, asdict

from PIL import Image, ImageDraw

from i18n import tr, DEEPL_TARGET

PROJECT_FILE = "project.json"
IMAGES_DIR = "images"

# Draft kinds (how the step's default sentence is produced)
KIND_BUTTON = "button"      # clicked a button-like control
KIND_INPUT = "input"        # clicked a text input field
KIND_OPEN = "open"          # clicked a menu/tab-like item
KIND_NAMED = "named"        # clicked a named control (generic click)
KIND_GENERIC = "generic"    # clicked somewhere with no name
KIND_MANUAL = "manual"      # manual screen capture (Mac / manual button)

_KIND_TEMPLATE = {
    KIND_BUTTON: "tpl_click_button",
    KIND_INPUT: "tpl_input",
    KIND_OPEN: "tpl_open",
    KIND_NAMED: "tpl_click_named",
    KIND_GENERIC: "tpl_click_generic",
    KIND_MANUAL: "tpl_manual",
}


@dataclass
class Rect:
    """A rectangle in relative coordinates (0..1 of image width/height)."""
    x: float
    y: float
    w: float
    h: float

    def to_pixels(self, img_w, img_h):
        x0 = max(0, int(round(self.x * img_w)))
        y0 = max(0, int(round(self.y * img_h)))
        x1 = min(img_w, int(round((self.x + self.w) * img_w)))
        y1 = min(img_h, int(round((self.y + self.h) * img_h)))
        return x0, y0, max(x0 + 1, x1), max(y0 + 1, y1)

    @staticmethod
    def from_pixels(x0, y0, x1, y1, img_w, img_h):
        if img_w <= 0 or img_h <= 0:
            return Rect(0.0, 0.0, 0.0, 0.0)
        x = min(x0, x1) / img_w
        y = min(y0, y1) / img_h
        w = abs(x1 - x0) / img_w
        h = abs(y1 - y0) / img_h
        return Rect(x, y, w, h)


@dataclass
class Step:
    image_file: str = ""                 # file name inside images/
    kind: str = KIND_MANUAL              # draft kind
    target_name: str = ""                # clicked control name (original)
    window_title: str = ""               # foreground window title
    click: tuple = None                  # (rel_x, rel_y) or None
    text_override: str = None            # user-written text (None = draft)
    memo: str = ""
    mosaics: list = field(default_factory=list)            # list[Rect]
    mosaic_candidates: list = field(default_factory=list)  # list[Rect]

    def draft_text(self, lang):
        key = _KIND_TEMPLATE.get(self.kind, "tpl_click_generic")
        if self.kind in (KIND_BUTTON, KIND_INPUT, KIND_OPEN, KIND_NAMED):
            return tr(lang, key, name=self.target_name)
        return tr(lang, key)

    def effective_text(self, lang):
        """The sentence shown for this step in language `lang`, before any
        optional machine translation of free text."""
        if self.text_override is not None:
            return self.text_override
        return self.draft_text(lang)

    def to_dict(self):
        d = asdict(self)
        d["click"] = list(self.click) if self.click else None
        return d

    @staticmethod
    def from_dict(d):
        step = Step(
            image_file=d.get("image_file", ""),
            kind=d.get("kind", KIND_MANUAL),
            target_name=d.get("target_name", ""),
            window_title=d.get("window_title", ""),
            text_override=d.get("text_override"),
            memo=d.get("memo", ""),
            mosaics=[Rect(**r) for r in d.get("mosaics", [])],
            mosaic_candidates=[Rect(**r)
                               for r in d.get("mosaic_candidates", [])],
        )
        click = d.get("click")
        if click:
            step.click = (float(click[0]), float(click[1]))
        return step


class Project:
    def __init__(self, title=""):
        self.title = title
        self.steps = []
        self.folder = None        # where the project is stored (or None)
        self._img_counter = 0

    # -- image handling -------------------------------------------------
    def _new_image_name(self):
        while True:
            self._img_counter += 1
            name = "step_%04d.png" % self._img_counter
            if all(s.image_file != name for s in self.steps):
                return name

    def add_step(self, step, pil_image=None):
        """Attach an image (PIL) to the step and append it. Images are
        kept in memory as files only after save(); until then the PIL
        image is stashed on the step object (not serialized)."""
        if not step.image_file:
            step.image_file = self._new_image_name()
        if pil_image is not None:
            step._pil = pil_image
        self.steps.append(step)
        return step

    # -- serialization --------------------------------------------------
    def to_dict(self):
        return {
            "version": 1,
            "title": self.title,
            "steps": [s.to_dict() for s in self.steps],
        }

    def save(self, folder):
        os.makedirs(folder, exist_ok=True)
        img_dir = os.path.join(folder, IMAGES_DIR)
        os.makedirs(img_dir, exist_ok=True)
        for step in self.steps:
            dest = os.path.join(img_dir, step.image_file)
            pil = getattr(step, "_pil", None)
            if pil is not None:
                pil.save(dest)
                step._pil = None
            elif not os.path.exists(dest) and self.folder:
                src = os.path.join(self.folder, IMAGES_DIR, step.image_file)
                if os.path.exists(src):
                    shutil.copyfile(src, dest)
        with open(os.path.join(folder, PROJECT_FILE), "w",
                  encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=1)
        self.folder = folder

    @staticmethod
    def load(folder):
        with open(os.path.join(folder, PROJECT_FILE), "r",
                  encoding="utf-8") as fh:
            data = json.load(fh)
        proj = Project(title=data.get("title", ""))
        proj.steps = [Step.from_dict(d) for d in data.get("steps", [])]
        proj.folder = folder
        nums = []
        for s in proj.steps:
            base = os.path.splitext(s.image_file)[0]
            if base.startswith("step_"):
                try:
                    nums.append(int(base[5:]))
                except ValueError:
                    pass
        proj._img_counter = max(nums) if nums else len(proj.steps)
        return proj

    def image_path(self, step):
        if self.folder:
            path = os.path.join(self.folder, IMAGES_DIR, step.image_file)
            if os.path.exists(path):
                return path
        return None

    def open_image(self, step):
        """Return a PIL Image for the step (from the in-memory stash or
        from the project folder)."""
        pil = getattr(step, "_pil", None)
        if pil is not None:
            return pil.copy()
        path = self.image_path(step)
        if path:
            with Image.open(path) as im:
                return im.convert("RGB")
        return None

    # -- ZIP ------------------------------------------------------------
    def export_zip(self, zip_path):
        tmp = None
        if self.folder is None:
            import tempfile
            tmp = tempfile.mkdtemp(prefix="tejun_")
            self.save(tmp)
            folder = tmp
        else:
            # make sure pending in-memory images are flushed
            self.save(self.folder)
            folder = self.folder
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _dirs, files in os.walk(folder):
                    for name in files:
                        full = os.path.join(root, name)
                        arc = os.path.relpath(full, folder)
                        zf.write(full, arc)
        finally:
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
                self.folder = None

    @staticmethod
    def import_zip(zip_path, dest_folder):
        os.makedirs(dest_folder, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                # guard against path traversal
                parts = [p for p in name.split("/") if p not in ("", ".", "..")]
                if not parts:
                    continue
                target = os.path.join(dest_folder, *parts)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        return Project.load(dest_folder)


# ----------------------------------------------------------------------
# Image rendering: marker + mosaics
# ----------------------------------------------------------------------

def apply_mosaics(image, rects, block=12):
    """Return a copy of the PIL image with the given relative rects
    pixelated. The original image is not modified."""
    out = image.copy()
    w, h = out.size
    for rect in rects:
        x0, y0, x1, y1 = rect.to_pixels(w, h)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        region = out.crop((x0, y0, x1, y1))
        small_w = max(1, (x1 - x0) // block)
        small_h = max(1, (y1 - y0) // block)
        region = region.resize((small_w, small_h), Image.BILINEAR)
        region = region.resize((x1 - x0, y1 - y0), Image.NEAREST)
        out.paste(region, (x0, y0))
    return out


def draw_marker(image, click, radius=None):
    """Return a copy with a red circle + dot at the relative click point."""
    if not click:
        return image
    out = image.copy()
    w, h = out.size
    cx, cy = int(click[0] * w), int(click[1] * h)
    r = radius or max(14, min(w, h) // 28)
    draw = ImageDraw.Draw(out)
    for off in range(3):
        draw.ellipse([cx - r - off, cy - r - off, cx + r + off, cy + r + off],
                     outline=(255, 40, 40))
    draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(255, 40, 40))
    return out


def render_step_image(project, step, show_marker=True):
    """The image as it will appear in an exported manual: mosaics applied,
    then (optionally) the click marker drawn on top."""
    img = project.open_image(step)
    if img is None:
        return None
    if step.mosaics:
        img = apply_mosaics(img, step.mosaics)
    if show_marker:
        img = draw_marker(img, step.click)
    return img


# ----------------------------------------------------------------------
# Password-field heuristic for mosaic candidates
# ----------------------------------------------------------------------

PASSWORD_WORDS = ("パスワード", "password", "passwd", "暗証", "pinコード")


def looks_like_password(name, is_password):
    if is_password:
        return True
    if not name:
        return False
    low = name.lower()
    return any(w in low for w in PASSWORD_WORDS)


# ----------------------------------------------------------------------
# Optional DeepL translation of free text
# ----------------------------------------------------------------------

class DeepLTranslator:
    """Translates free text with the user's own DeepL API key. Only used
    when a key is configured; any failure raises DeepLError and the caller
    falls back to the original text."""

    class DeepLError(Exception):
        pass

    def __init__(self, api_key, timeout=20):
        self.api_key = (api_key or "").strip()
        self.timeout = timeout

    @property
    def configured(self):
        return bool(self.api_key)

    def _endpoint(self):
        host = "api-free.deepl.com" if self.api_key.endswith(":fx") \
            else "api.deepl.com"
        return "https://%s/v2/translate" % host

    def translate(self, text, target_lang):
        """target_lang is our language code. Languages DeepL does not
        support (Arabic) raise DeepLError so the caller keeps the
        original text."""
        code = DEEPL_TARGET.get(target_lang)
        if not code or not text or not text.strip():
            raise self.DeepLError("unsupported or empty")
        data = urllib.parse.urlencode(
            {"text": text, "target_lang": code}).encode("utf-8")
        req = urllib.request.Request(
            self._endpoint(), data=data,
            headers={"Authorization": "DeepL-Auth-Key " + self.api_key,
                     "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return payload["translations"][0]["text"]
        except Exception as exc:  # network, HTTP, malformed reply
            raise self.DeepLError(str(exc))


def resolve_step_texts(project, lang, translator=None, use_deepl=False):
    """Return (texts, any_free_text, translate_failed) for export in
    `lang`. Draft sentences are rendered from the translated templates.
    Free text stays in the original language unless a DeepL translator is
    configured and enabled; failures keep the original and set the flag.
    Arabic has no DeepL target and always keeps the original."""
    texts = []
    any_free = False
    failed = False
    for step in project.steps:
        if step.text_override is None:
            texts.append(step.draft_text(lang))
            continue
        any_free = True
        text = step.text_override
        if use_deepl and translator is not None and translator.configured:
            try:
                text = translator.translate(text, lang)
            except DeepLTranslator.DeepLError:
                failed = True
        texts.append(text)
    return texts, any_free, failed

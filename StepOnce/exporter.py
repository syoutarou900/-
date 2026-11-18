# -*- coding: utf-8 -*-
"""Manual export for StepOnce.

For each selected language a complete manual is produced:
- PDF via Qt's QPdfWriter + QTextDocument (no extra dependency).
- Word .docx written directly as OOXML with the standard library only
  (a .docx is a ZIP of XML), so the app needs no python-docx at runtime.

Fixed phrases (cover, TOC heading, step headings, notes) come from the
translated strings in i18n.py; control names are inserted in their
original language; user-written free text stays in its original language
unless the optional DeepL translation is enabled and succeeds.
"""

import datetime
import html
import os
import re
import tempfile
import zipfile
from xml.sax.saxutils import escape as xml_escape

import core
from appinfo import display_name
from i18n import tr


def _file_stem(title):
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (title or "").strip())
    stem = stem.strip(". ")
    return stem or "manual"


def build_manual_model(project, lang, translator=None, use_deepl=False):
    """All text content of one language's manual, ready for rendering."""
    texts, any_free, failed = core.resolve_step_texts(
        project, lang, translator=translator, use_deepl=use_deepl)
    title = project.title.strip() or tr(lang, "m_untitled")
    steps = []
    for idx, step in enumerate(project.steps):
        steps.append({
            "n": idx + 1,
            "heading": tr(lang, "m_step", n=idx + 1),
            "text": texts[idx],
            "memo": step.memo,
            "window_title": step.window_title,
            "has_click": step.click is not None,
            "step": step,
        })
    return {
        "lang": lang,
        "title": title,
        "manual_label": tr(lang, "m_manual"),
        "created_with": tr(lang, "m_created_with",
                           app=display_name(lang)),
        "date_line": tr(lang, "m_date",
                        date=datetime.date.today().isoformat()),
        "toc_title": tr(lang, "m_toc"),
        "memo_label": tr(lang, "m_memo"),
        "window_label": tr(lang, "m_window"),
        "note_freetext": tr(lang, "m_note_freetext") if any_free else "",
        "note_marker": tr(lang, "m_note_marker"),
        "steps": steps,
        "translate_failed": failed,
    }


# ----------------------------------------------------------------------
# PDF (Qt)
# ----------------------------------------------------------------------

def _manual_html(model, image_names, image_widths=None):
    image_widths = image_widths or {}
    lang = model["lang"]
    rtl = lang == "ar"
    direction = "rtl" if rtl else "ltr"
    align = "right" if rtl else "left"
    parts = ["<html><head><meta charset='utf-8'></head>"
             "<body dir='%s' style='font-family: sans-serif;'>" % direction]
    parts.append("<h1 align='center'>%s</h1>"
                 % html.escape(model["title"]))
    parts.append("<h2 align='center'>%s</h2>"
                 % html.escape(model["manual_label"]))
    parts.append("<p align='center'>%s<br/>%s</p>"
                 % (html.escape(model["created_with"]),
                    html.escape(model["date_line"])))
    if model["note_freetext"]:
        parts.append("<p align='%s'><i>%s</i></p>"
                     % (align, html.escape(model["note_freetext"])))
    if any(s["has_click"] for s in model["steps"]):
        parts.append("<p align='%s'><i>%s</i></p>"
                     % (align, html.escape(model["note_marker"])))
    parts.append("<h3 align='%s'>%s</h3>"
                 % (align, html.escape(model["toc_title"])))
    for s in model["steps"]:
        toc_line = "%s: %s" % (s["heading"], s["text"])
        parts.append("<p align='%s'>%s</p>"
                     % (align, html.escape(toc_line[:90])))
    parts.append("<br/>")
    for s in model["steps"]:
        parts.append("<h3 align='%s'>%s</h3>"
                     % (align, html.escape(s["heading"])))
        img_name = image_names.get(s["n"])
        if img_name:
            width = image_widths.get(s["n"])
            if width:
                parts.append("<p align='center'><img src='%s' width='%d'/>"
                             "</p>" % (img_name, width))
            else:
                parts.append("<p align='center'><img src='%s'/></p>"
                             % img_name)
        parts.append("<p align='%s'>%s</p>" % (align, html.escape(s["text"])))
        if s["window_title"]:
            parts.append("<p align='%s'><i>%s: %s</i></p>"
                         % (align, html.escape(model["window_label"]),
                            html.escape(s["window_title"])))
        if s["memo"]:
            parts.append("<p align='%s'><i>%s: %s</i></p>"
                         % (align, html.escape(model["memo_label"]),
                            html.escape(s["memo"])))
    parts.append("</body></html>")
    return "".join(parts)


def write_pdf(project, model, out_path, show_marker=True, tmp_dir=None):
    from PySide6.QtCore import QSizeF, QUrl
    from PySide6.QtGui import (QGuiApplication, QPageLayout, QPageSize,
                               QPdfWriter, QTextDocument)
    from PySide6.QtCore import QMarginsF

    tmp_dir = tmp_dir or tempfile.mkdtemp(prefix="tejun_pdf_")
    writer = QPdfWriter(out_path)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setResolution(120)
    writer.setPageMargins(QMarginsF(15, 15, 15, 15),
                          QPageLayout.Unit.Millimeter)
    page_rect = writer.pageLayout().paintRectPixels(120)
    content_w = page_rect.width()

    image_names = {}
    image_widths = {}
    doc = QTextDocument()
    for s in model["steps"]:
        img = core.render_step_image(project, s["step"],
                                     show_marker=show_marker)
        if img is None:
            continue
        name = "step_%d.png" % s["n"]
        path = os.path.join(tmp_dir, name)
        if img.width > content_w:
            disp_w = content_w
            img = img.resize(
                (disp_w, int(img.height * disp_w / img.width)))
        else:
            disp_w = img.width
        img.save(path)
        image_names[s["n"]] = name
        image_widths[s["n"]] = disp_w
    html_text = _manual_html(model, image_names, image_widths)
    doc.setHtml(html_text)
    for name in image_names.values():
        from PySide6.QtGui import QImage
        doc.addResource(QTextDocument.ImageResource, QUrl(name),
                        QImage(os.path.join(tmp_dir, name)))
    doc.setPageSize(QSizeF(page_rect.width(), page_rect.height()))
    doc.print_(writer)
    return out_path


# ----------------------------------------------------------------------
# Word .docx (raw OOXML, standard library only)
# ----------------------------------------------------------------------

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"

_MAX_IMG_W_EMU = 5_750_000  # ~14.6 cm, fits A4 with 2 cm margins


def _p(text, size=22, bold=False, italic=False, align=None,
       space_after=120):
    jc = "<w:jc w:val=\"%s\"/>" % align if align else ""
    rpr = "<w:rPr>%s%s<w:sz w:val=\"%d\"/><w:szCs w:val=\"%d\"/></w:rPr>" % (
        "<w:b/>" if bold else "", "<w:i/>" if italic else "", size, size)
    return ("<w:p><w:pPr>%s<w:spacing w:after=\"%d\"/></w:pPr>"
            "<w:r>%s<w:t xml:space=\"preserve\">%s</w:t></w:r></w:p>"
            % (jc, space_after, rpr, xml_escape(text)))


def _p_image(rel_id, cx, cy):
    return (
        "<w:p><w:pPr><w:jc w:val=\"center\"/></w:pPr><w:r><w:drawing>"
        "<wp:inline distT=\"0\" distB=\"0\" distL=\"0\" distR=\"0\">"
        "<wp:extent cx=\"%d\" cy=\"%d\"/>"
        "<wp:docPr id=\"%s\" name=\"image\"/>"
        "<a:graphic><a:graphicData uri=\"%s\">"
        "<pic:pic><pic:nvPicPr><pic:cNvPr id=\"%s\" name=\"image\"/>"
        "<pic:cNvPicPr/></pic:nvPicPr>"
        "<pic:blipFill><a:blip r:embed=\"%s\"/><a:stretch><a:fillRect/>"
        "</a:stretch></pic:blipFill>"
        "<pic:spPr><a:xfrm><a:off x=\"0\" y=\"0\"/>"
        "<a:ext cx=\"%d\" cy=\"%d\"/></a:xfrm>"
        "<a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></pic:spPr>"
        "</pic:pic></a:graphicData></a:graphic></wp:inline>"
        "</w:drawing></w:r></w:p>"
        % (cx, cy, rel_id[3:], _PIC_NS, rel_id[3:], rel_id, cx, cy))


def write_docx(project, model, out_path, show_marker=True, tmp_dir=None):
    from PIL import Image
    tmp_dir = tmp_dir or tempfile.mkdtemp(prefix="tejun_docx_")
    rtl = model["lang"] == "ar"
    align = "right" if rtl else "left"
    body = []
    body.append(_p(model["title"], size=44, bold=True, align="center"))
    body.append(_p(model["manual_label"], size=30, bold=True,
                   align="center"))
    body.append(_p(model["created_with"], size=20, align="center"))
    body.append(_p(model["date_line"], size=20, align="center"))
    if model["note_freetext"]:
        body.append(_p(model["note_freetext"], size=18, italic=True,
                       align=align))
    if any(s["has_click"] for s in model["steps"]):
        body.append(_p(model["note_marker"], size=18, italic=True,
                       align=align))
    body.append(_p(model["toc_title"], size=28, bold=True, align=align))
    for s in model["steps"]:
        body.append(_p("%s: %s" % (s["heading"], s["text"][:90]),
                       size=20, align=align))

    rels = []
    images = []  # (arcname, path)
    for s in model["steps"]:
        body.append(_p(s["heading"], size=28, bold=True, align=align,
                       space_after=80))
        img = core.render_step_image(project, s["step"],
                                     show_marker=show_marker)
        if img is not None:
            name = "image%d.png" % s["n"]
            path = os.path.join(tmp_dir, name)
            img.save(path)
            rel_id = "rId%d" % (len(rels) + 1)
            rels.append((rel_id, "word/media/" + name))
            images.append(("word/media/" + name, path))
            w, h = img.size
            cx = _MAX_IMG_W_EMU
            cy = int(cx * h / w) if w else cx
            body.append(_p_image(rel_id, cx, cy))
        body.append(_p(s["text"], size=22, align=align))
        if s["window_title"]:
            body.append(_p("%s: %s" % (model["window_label"],
                                       s["window_title"]),
                           size=18, italic=True, align=align))
        if s["memo"]:
            body.append(_p("%s: %s" % (model["memo_label"], s["memo"]),
                           size=18, italic=True, align=align))

    sect = ("<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/>"
            "<w:pgMar w:top=\"1134\" w:right=\"1134\" w:bottom=\"1134\" "
            "w:left=\"1134\"/></w:sectPr>")
    document_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document xmlns:w=\"%s\" xmlns:r=\"%s\" xmlns:wp=\"%s\" "
        "xmlns:a=\"%s\" xmlns:pic=\"%s\"><w:body>%s%s</w:body></w:document>"
        % (_W_NS, _R_NS, _WP_NS, _A_NS, _PIC_NS, "".join(body), sect))
    rels_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/"
        "2006/relationships\">%s</Relationships>"
        % "".join(
            "<Relationship Id=\"%s\" Type=\"%s/image\" Target=\"%s\"/>"
            % (rid, _R_NS, target.replace("word/", ""))
            for rid, target in rels))
    content_types = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/"
        "content-types\">"
        "<Default Extension=\"rels\" ContentType=\"application/vnd.openxml"
        "formats-package.relationships+xml\"/>"
        "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
        "<Default Extension=\"png\" ContentType=\"image/png\"/>"
        "<Override PartName=\"/word/document.xml\" ContentType=\""
        "application/vnd.openxmlformats-officedocument.wordprocessingml."
        "document.main+xml\"/></Types>")
    root_rels = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/"
        "2006/relationships\">"
        "<Relationship Id=\"rId1\" Type=\"%s/officeDocument\" "
        "Target=\"word/document.xml\"/></Relationships>" % _R_NS)

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", rels_xml)
        for arcname, path in images:
            zf.write(path, arcname)
    return out_path


# ----------------------------------------------------------------------
# Batch export
# ----------------------------------------------------------------------

class ExportResult:
    def __init__(self):
        self.files = []
        self.translate_failed = False


def export_manuals(project, out_dir, langs, formats, show_marker=True,
                   translator=None, use_deepl=False):
    os.makedirs(out_dir, exist_ok=True)
    result = ExportResult()
    stem = _file_stem(project.title)
    for lang in langs:
        model = build_manual_model(project, lang, translator=translator,
                                   use_deepl=use_deepl)
        if model["translate_failed"]:
            result.translate_failed = True
        if "pdf" in formats:
            path = os.path.join(out_dir, "%s_%s.pdf" % (stem, lang))
            write_pdf(project, model, path, show_marker=show_marker)
            result.files.append(path)
        if "docx" in formats:
            path = os.path.join(out_dir, "%s_%s.docx" % (stem, lang))
            write_docx(project, model, path, show_marker=show_marker)
            result.files.append(path)
    return result

# -*- coding: utf-8 -*-
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def test_ui_smoke(tmp_path, monkeypatch):
    import core
    monkeypatch.setattr(core, "APP_DIR", Path(__file__).resolve().parent.parent)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import app as appmod
    # point settings to tmp
    w = appmod.MainWindow()
    w.settings["output_base"] = str(tmp_path / "out")
    w.settings["project"] = "作業"
    # sample files
    from PIL import Image
    img = tmp_path/"p.png"; Image.new("RGB", (1600, 800), (0, 128, 0)).save(img)
    outs = w.process_files("image", [img]); assert outs and Path(outs[0]).exists()
    import fitz
    doc = fitz.open(); pg = doc.new_page(); pg.insert_text((72, 72), "UI test")
    pdf = tmp_path/"u.pdf"; doc.save(pdf); doc.close()
    outs = w.process_files("transcribe", [pdf]); assert outs
    merged = w.process_files("pdf_merge", [pdf]); assert Path(merged).exists()
    f = tmp_path/"z.txt"; f.write_text("zip me")
    z = w.process_files("zip", [f]); assert z and Path(z[0]).exists()
    ex = w.process_files("unzip", z); assert ex and Path(ex[0]).exists()
    w.close()

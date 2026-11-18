# -*- coding: utf-8 -*-
"""Tests for StepOnce.

Run: python3 -m unittest discover -s tests -v   (from the app folder)
GUI tests use the offscreen Qt platform.
"""

import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402

import core  # noqa: E402
import i18n  # noqa: E402
import recorder as recorder_mod  # noqa: E402
from core import Project, Rect, Step  # noqa: E402


def sample_image(w=200, h=100, color=(240, 240, 240)):
    return Image.new("RGB", (w, h), color)


class TestI18n(unittest.TestCase):
    def test_all_languages_have_all_keys(self):
        ref = set(i18n.STRINGS["ja"])
        for code in i18n.LANG_ORDER:
            self.assertEqual(set(i18n.STRINGS[code]), ref, code)

    def test_templates_render_in_all_languages(self):
        for code in i18n.LANG_ORDER:
            for kind, key in (("button", "tpl_click_button"),
                              ("input", "tpl_input"),
                              ("open", "tpl_open"),
                              ("named", "tpl_click_named")):
                text = i18n.tr(code, key, name="OK")
                self.assertIn("OK", text, (code, key))
                self.assertTrue(text.strip(), (code, key))
            generic = i18n.tr(code, "tpl_click_generic")
            self.assertTrue(generic.strip(), code)

    def test_draft_text_per_kind(self):
        step = Step(kind=core.KIND_BUTTON, target_name="保存")
        self.assertEqual(step.draft_text("ja"),
                         "『保存』ボタンをクリックします")
        self.assertEqual(step.draft_text("en"),
                         "Click the “保存” button")
        step2 = Step(kind=core.KIND_INPUT, target_name="名前")
        self.assertIn("名前", step2.draft_text("ko"))


class TestRecorderPipeline(unittest.TestCase):
    def _recorder(self):
        captured = []
        rec = recorder_mod.FakeRecorder(
            lambda step, img: captured.append((step, img)))
        rec.start()
        return rec, captured

    def test_button_click_makes_button_draft(self):
        rec, captured = self._recorder()
        el = recorder_mod.ElementInfo(
            name="OK", control_type=50000, rect=(10, 10, 80, 30),
            window_title="設定")
        rec.feed(sample_image(), el, (50, 25))
        step, _img = captured[0]
        self.assertEqual(step.kind, core.KIND_BUTTON)
        self.assertEqual(step.target_name, "OK")
        self.assertEqual(step.window_title, "設定")
        self.assertAlmostEqual(step.click[0], 0.25)
        self.assertAlmostEqual(step.click[1], 0.25)

    def test_edit_click_makes_input_draft(self):
        rec, captured = self._recorder()
        el = recorder_mod.ElementInfo(name="検索", control_type=50004)
        rec.feed(sample_image(), el, (20, 20))
        self.assertEqual(captured[0][0].kind, core.KIND_INPUT)

    def test_menu_click_makes_open_draft(self):
        rec, captured = self._recorder()
        el = recorder_mod.ElementInfo(name="ファイル", control_type=50011)
        rec.feed(sample_image(), el, (20, 20))
        self.assertEqual(captured[0][0].kind, core.KIND_OPEN)

    def test_nameless_click_is_generic(self):
        rec, captured = self._recorder()
        el = recorder_mod.ElementInfo(name="", control_type=50000)
        rec.feed(sample_image(), el, (20, 20))
        step = captured[0][0]
        self.assertEqual(step.kind, core.KIND_GENERIC)
        self.assertEqual(step.draft_text("ja"), "画面をクリックします")

    def test_password_field_becomes_mosaic_candidate_only(self):
        rec, captured = self._recorder()
        el = recorder_mod.ElementInfo(
            name="パスワード", control_type=50004, is_password=True,
            rect=(20, 20, 100, 24))
        rec.feed(sample_image(), el, (50, 30))
        step = captured[0][0]
        self.assertEqual(len(step.mosaic_candidates), 1)
        self.assertEqual(step.mosaics, [])  # never auto-applied

    def test_password_name_heuristic(self):
        self.assertTrue(core.looks_like_password("Password", False))
        self.assertTrue(core.looks_like_password("パスワード", False))
        self.assertFalse(core.looks_like_password("ユーザー名", False))
        self.assertTrue(core.looks_like_password("", True))

    def test_paused_recorder_drops_clicks(self):
        rec, captured = self._recorder()
        rec.set_paused(True)
        rec.feed(sample_image(), None, (1, 1))
        self.assertEqual(captured, [])

    def test_windows_recorder_ignores_own_process(self):
        class FakeProvider:
            def element_from_point(self, x, y):
                return recorder_mod.ElementInfo(
                    name="X", control_type=50000,
                    process_id=os.getpid())
        got = []
        rec = recorder_mod.WindowsAutoRecorder(
            lambda s, i: got.append(s), element_provider=FakeProvider(),
            grabber=lambda: (sample_image(), (0, 0)))
        self.assertIsNone(rec.process_click(5, 5))
        self.assertEqual(got, [])

    def test_windows_recorder_processes_other_process(self):
        class FakeProvider:
            def element_from_point(self, x, y):
                return recorder_mod.ElementInfo(
                    name="送信", control_type=50000, process_id=999999)
        got = []
        rec = recorder_mod.WindowsAutoRecorder(
            lambda s, i: got.append(s), element_provider=FakeProvider(),
            grabber=lambda: (sample_image(), (0, 0)))
        step = rec.process_click(5, 5)
        self.assertIsNotNone(step)
        self.assertEqual(step.target_name, "送信")


class TestMosaicAndMarker(unittest.TestCase):
    def test_mosaic_changes_only_region(self):
        img = sample_image(100, 100, (200, 200, 200))
        # put a sharp pattern inside the region
        for x in range(10, 40):
            img.putpixel((x, 10), (0, 0, 0) if x % 2 else (255, 255, 255))
        out = core.apply_mosaics(img, [Rect(0.1, 0.1, 0.3, 0.3)])
        self.assertEqual(img.getpixel((11, 10)), (0, 0, 0))  # original kept
        region_vals = {out.getpixel((x, 10)) for x in range(12, 38, 3)}
        self.assertLess(len(region_vals), 4)  # pixelated -> few colors
        self.assertEqual(out.getpixel((90, 90)), (200, 200, 200))

    def test_marker_drawn_at_click(self):
        img = sample_image(200, 200, (255, 255, 255))
        out = core.draw_marker(img, (0.5, 0.5))
        r, g, b = out.getpixel((100, 100))
        self.assertGreater(r, 200)
        self.assertLess(g, 80)
        self.assertEqual(img.getpixel((100, 100)), (255, 255, 255))
        self.assertIs(core.draw_marker(img, None), img)


class TestProjectIO(unittest.TestCase):
    def _project(self):
        proj = Project(title="テスト手順")
        s1 = Step(kind=core.KIND_BUTTON, target_name="OK",
                  window_title="設定", click=(0.5, 0.25),
                  mosaics=[Rect(0.1, 0.1, 0.2, 0.2)],
                  mosaic_candidates=[Rect(0.3, 0.3, 0.1, 0.1)],
                  memo="メモ1")
        proj.add_step(s1, sample_image())
        s2 = Step(kind=core.KIND_MANUAL, text_override="自分で書いた文")
        proj.add_step(s2, sample_image(120, 80, (10, 20, 30)))
        return proj

    def test_folder_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = os.path.join(tmp, "proj")
            self._project().save(folder)
            loaded = Project.load(folder)
            self.assertEqual(loaded.title, "テスト手順")
            self.assertEqual(len(loaded.steps), 2)
            s1, s2 = loaded.steps
            self.assertEqual(s1.target_name, "OK")
            self.assertEqual(s1.click, (0.5, 0.25))
            self.assertEqual(len(s1.mosaics), 1)
            self.assertEqual(len(s1.mosaic_candidates), 1)
            self.assertEqual(s1.memo, "メモ1")
            self.assertEqual(s2.text_override, "自分で書いた文")
            img = loaded.open_image(s1)
            self.assertEqual(img.size, (200, 100))

    def test_zip_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "proj.zip")
            self._project().export_zip(zip_path)
            self.assertTrue(zipfile_ok(zip_path))
            loaded = Project.import_zip(zip_path, os.path.join(tmp, "out"))
            self.assertEqual(loaded.title, "テスト手順")
            self.assertEqual(len(loaded.steps), 2)

    def test_render_applies_mosaic_and_marker(self):
        proj = self._project()
        out = core.render_step_image(proj, proj.steps[0])
        self.assertIsNotNone(out)
        self.assertEqual(out.size, (200, 100))


def zipfile_ok(path):
    import zipfile
    with zipfile.ZipFile(path) as zf:
        return "project.json" in zf.namelist()


class _StubTranslator:
    def __init__(self, fail=False):
        self.configured = True
        self.fail = fail

    def translate(self, text, lang):
        if self.fail:
            raise core.DeepLTranslator.DeepLError("stub failure")
        return "[%s] %s" % (lang, text)


class TestFreeTextResolution(unittest.TestCase):
    def _proj(self):
        proj = Project(title="t")
        proj.add_step(Step(kind=core.KIND_BUTTON, target_name="OK"),
                      sample_image())
        proj.add_step(Step(kind=core.KIND_MANUAL,
                           text_override="自由な文"), sample_image())
        return proj

    def test_free_text_kept_without_deepl(self):
        texts, any_free, failed = core.resolve_step_texts(
            self._proj(), "en")
        self.assertEqual(texts[1], "自由な文")
        self.assertTrue(any_free)
        self.assertFalse(failed)

    def test_free_text_translated_with_stub(self):
        texts, _any_free, failed = core.resolve_step_texts(
            self._proj(), "en", translator=_StubTranslator(),
            use_deepl=True)
        self.assertEqual(texts[1], "[en] 自由な文")
        self.assertFalse(failed)

    def test_translation_failure_falls_back(self):
        texts, _any_free, failed = core.resolve_step_texts(
            self._proj(), "en", translator=_StubTranslator(fail=True),
            use_deepl=True)
        self.assertEqual(texts[1], "自由な文")
        self.assertTrue(failed)

    def test_arabic_never_translated(self):
        class RealishTranslator(core.DeepLTranslator):
            def __init__(self):
                super().__init__("dummy:fx")
        texts, _f, failed = core.resolve_step_texts(
            self._proj(), "ar", translator=RealishTranslator(),
            use_deepl=True)
        self.assertEqual(texts[1], "自由な文")
        self.assertTrue(failed)  # unsupported -> original kept, flagged


class TestExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _proj(self):
        proj = Project(title="Export Test")
        proj.add_step(Step(kind=core.KIND_BUTTON, target_name="保存",
                           window_title="設定", click=(0.5, 0.5),
                           mosaics=[Rect(0.1, 0.1, 0.3, 0.2)]),
                      sample_image(320, 200, (230, 230, 250)))
        proj.add_step(Step(kind=core.KIND_MANUAL,
                           text_override="確認してから進みます",
                           memo="注意メモ"),
                      sample_image(320, 200, (250, 240, 230)))
        return proj

    def test_export_all_languages_pdf_and_docx(self):
        import exporter
        with tempfile.TemporaryDirectory() as tmp:
            result = exporter.export_manuals(
                self._proj(), tmp, i18n.LANG_ORDER, ["pdf", "docx"])
            self.assertEqual(len(result.files), 26)
            for path in result.files:
                self.assertTrue(os.path.getsize(path) > 1000, path)
                if path.endswith(".pdf"):
                    with open(path, "rb") as fh:
                        self.assertEqual(fh.read(4), b"%PDF")

    def test_docx_content(self):
        import docx  # python-docx is a test-only verifier
        import exporter
        with tempfile.TemporaryDirectory() as tmp:
            result = exporter.export_manuals(
                self._proj(), tmp, ["ja", "en"], ["docx"])
            ja = [p for p in result.files if p.endswith("_ja.docx")][0]
            doc = docx.Document(ja)
            full = "\n".join(p.text for p in doc.paragraphs)
            self.assertIn("『保存』ボタンをクリックします", full)
            self.assertIn("確認してから進みます", full)
            en = [p for p in result.files if p.endswith("_en.docx")][0]
            doc_en = docx.Document(en)
            full_en = "\n".join(p.text for p in doc_en.paragraphs)
            self.assertIn("Click the “保存” button", full_en)
            self.assertIn("確認してから進みます", full_en)  # free text kept
            import zipfile
            with zipfile.ZipFile(ja) as zf:
                media = [n for n in zf.namelist()
                         if n.startswith("word/media/")]
            self.assertEqual(len(media), 2)


class TestGuiSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _window(self):
        import app as app_mod
        win = app_mod.MainWindow()
        self.addCleanup(win.close)
        return win

    def _add_steps(self, win):
        for i in range(3):
            step = Step(kind=core.KIND_BUTTON,
                        target_name="B%d" % i)
            win.project.add_step(step, sample_image(160, 100))
        win._refresh_steps()

    def test_window_builds_and_lists_steps(self):
        win = self._window()
        self._add_steps(win)
        self.assertEqual(win.list_steps.count(), 3)
        win.list_steps.setCurrentRow(1)
        self.assertIsNotNone(win.current_step)
        self.assertEqual(win.current_step.target_name, "B1")

    def test_step_operations(self):
        win = self._window()
        self._add_steps(win)
        win.list_steps.setCurrentRow(0)
        win.move_step(1)
        self.assertEqual(win.project.steps[0].target_name, "B1")
        self.assertEqual(win.project.steps[1].target_name, "B0")
        win.list_steps.setCurrentRow(1)
        win.duplicate_step()
        self.assertEqual(len(win.project.steps), 4)
        win.list_steps.setCurrentRow(0)
        win.delete_step()
        self.assertEqual(len(win.project.steps), 3)

    def test_editor_edit_becomes_override(self):
        win = self._window()
        self._add_steps(win)
        win.list_steps.setCurrentRow(0)
        win.edit_text.setPlainText("書き直した文")
        win._commit_editor()
        self.assertEqual(win.project.steps[0].text_override,
                         "書き直した文")

    def test_language_switch_instant_and_rtl(self):
        from PySide6.QtCore import Qt
        win = self._window()
        ja_text = win.btn_record.text()
        win.combo_lang.setCurrentIndex(i18n.LANG_ORDER.index("en"))
        self.assertEqual(win.lang, "en")
        self.assertNotEqual(win.btn_record.text(), ja_text)
        self.assertIn("Start recording", win.btn_record.text())
        win.combo_lang.setCurrentIndex(i18n.LANG_ORDER.index("ar"))
        self.assertEqual(win.layoutDirection(),
                         Qt.LayoutDirection.RightToLeft)
        win.combo_lang.setCurrentIndex(i18n.LANG_ORDER.index("ja"))
        self.assertEqual(win.layoutDirection(),
                         Qt.LayoutDirection.LeftToRight)

    def test_panel_retranslates(self):
        import app as app_mod
        panel = app_mod.RecordPanel("ja", manual_mode=True)
        self.addCleanup(panel.close)
        panel.set_count(3)
        ja = panel.btn_finish.text()
        panel.retranslate("en")
        self.assertNotEqual(panel.btn_finish.text(), ja)
        self.assertIn("3", panel.lbl_count.text())

    def test_dialogs_build(self):
        import app as app_mod
        win = self._window()
        dlg = app_mod.ExportDialog(win, "ja", has_deepl_key=False)
        self.addCleanup(dlg.close)
        opts = dlg.options()
        self.assertEqual(len(opts["langs"]), 13)
        self.assertIn("pdf", opts["formats"])
        sd = app_mod.SettingsDialog(win, "ja", "")
        self.addCleanup(sd.close)


if __name__ == "__main__":
    unittest.main()

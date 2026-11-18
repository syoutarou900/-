# -*- coding: utf-8 -*-
"""Tests for the Tesseract resolution order (env override > bundled >
system PATH) and OCR language selection. Pure Python, no real tesseract
needed: fake executables are empty files in tmp folders."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake")
    return str(path)


def test_env_override_wins(tmp_path):
    env_exe = _touch(tmp_path / "custom" / "tesseract.exe")
    _touch(tmp_path / "app" / "tesseract" / "tesseract.exe")
    found = core.find_tesseract(
        env={"TRANSCRIBEGUARD_TESSERACT_CMD": env_exe},
        frozen=False, app_dir=str(tmp_path / "app"),
        which=lambda name: None)
    assert found == env_exe


def test_env_override_alt_name(tmp_path):
    env_exe = _touch(tmp_path / "custom" / "myocr.exe")
    found = core.find_tesseract(
        env={"TRANSCRIBEGUARD_TESSERACT": env_exe},
        frozen=False, app_dir=str(tmp_path / "app"),
        which=lambda name: None)
    assert found == env_exe


def test_frozen_bundled_beats_source_dir(tmp_path):
    exe_dir = tmp_path / "dist"
    bundled = _touch(exe_dir / "tesseract" / "tesseract.exe")
    _touch(tmp_path / "src" / "tesseract" / "tesseract.exe")
    found = core.find_tesseract(
        env={}, frozen=True, exe_dir=str(exe_dir),
        app_dir=str(tmp_path / "src"), which=lambda name: None)
    assert found == bundled


def test_source_bundled_next_to_app(tmp_path):
    bundled = _touch(tmp_path / "tesseract" / "tesseract.exe")
    found = core.find_tesseract(
        env={}, frozen=False, app_dir=str(tmp_path),
        which=lambda name: None)
    assert found == bundled


def test_path_fallback(tmp_path):
    found = core.find_tesseract(
        env={}, frozen=False, app_dir=str(tmp_path),
        which=lambda name: "/usr/bin/tesseract" if name == "tesseract" else None)
    assert found == "/usr/bin/tesseract"


def test_not_found_anywhere(tmp_path):
    found = core.find_tesseract(
        env={}, frozen=False, app_dir=str(tmp_path),
        which=lambda name: None)
    assert found is None


def test_find_tessdata_dir_bundled(tmp_path):
    td = tmp_path / "tesseract" / "tessdata"
    td.mkdir(parents=True)
    (td / "jpn.traineddata").write_bytes(b"x")
    found = core.find_tessdata_dir(
        env={}, frozen=False, app_dir=str(tmp_path))
    assert found == str(td)


def test_find_tessdata_dir_env_override(tmp_path):
    td = tmp_path / "mydata"
    td.mkdir()
    (td / "eng.traineddata").write_bytes(b"x")
    found = core.find_tessdata_dir(
        env={"TRANSCRIBEGUARD_TESSDATA_DIR": str(td)},
        frozen=False, app_dir=str(tmp_path / "app"))
    assert found == str(td)


def test_ocr_lang_string_defaults_and_ui():
    assert core.ocr_lang_string("ja") == "jpn+eng"
    assert core.ocr_lang_string("en") == "jpn+eng"
    assert core.ocr_lang_string("ko") == "jpn+eng+kor"
    assert core.ocr_lang_string("zh_CN") == "jpn+eng+chi_sim"
    assert core.ocr_lang_string("ar") == "jpn+eng+ara"


def test_ocr_lang_string_filters_to_available_data(tmp_path):
    (tmp_path / "jpn.traineddata").write_bytes(b"x")
    (tmp_path / "eng.traineddata").write_bytes(b"x")
    # kor has no data file here -> dropped from the language string
    assert core.ocr_lang_string("ko", str(tmp_path)) == "jpn+eng"
    (tmp_path / "kor.traineddata").write_bytes(b"x")
    assert core.ocr_lang_string("ko", str(tmp_path)) == "jpn+eng+kor"


def test_darwin_candidates_ignore_windows_bundled_exe(tmp_path):
    _touch(tmp_path / "tesseract" / "tesseract.exe")
    cands = core.tesseract_candidates(
        env={}, frozen=False, app_dir=str(tmp_path), platform="darwin")
    assert str(tmp_path / "tesseract" / "tesseract.exe") not in cands
    assert str(tmp_path / "tesseract" / "tesseract") in cands
    assert cands[-2:] == list(core._MAC_TESSERACT_PATHS)


def test_darwin_homebrew_paths_are_checked_before_path(tmp_path, monkeypatch):
    apple_silicon = _touch(tmp_path / "opt" / "homebrew" / "bin" / "tesseract")
    intel = _touch(tmp_path / "usr" / "local" / "bin" / "tesseract")
    monkeypatch.setattr(core, "_MAC_TESSERACT_PATHS", (apple_silicon, intel))
    found = core.find_tesseract(
        env={}, frozen=False, app_dir=str(tmp_path / "app"),
        which=lambda name: "/should/not/win", platform="darwin")
    assert found == apple_silicon


def test_non_darwin_candidates_do_not_include_homebrew(tmp_path):
    cands = core.tesseract_candidates(
        env={}, frozen=False, app_dir=str(tmp_path), platform="win32")
    assert not any(c in core._MAC_TESSERACT_PATHS for c in cands)
    assert str(tmp_path / "tesseract" / "tesseract.exe") in cands

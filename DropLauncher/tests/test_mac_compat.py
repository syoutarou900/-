# -*- coding: utf-8 -*-
"""macOS (darwin) branch tests for the DropLauncher retrofit.

These tests simulate sys.platform == "darwin" on a Linux host and verify
that the Mac branches resolve the macOS-standard locations, while the
Windows branches keep their exact original behaviour.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import core


def test_app_base_dir_darwin(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    base = core.app_base_dir()
    assert base == tmp_path / "Library" / "Application Support" / "DropLauncher"
    assert base.is_dir()


def test_app_base_dir_non_darwin_unchanged(monkeypatch, tmp_path):
    # On non-darwin the writable APP_DIR (portable) behaviour stays as before.
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(core, "APP_DIR", tmp_path)
    assert core.app_base_dir() == tmp_path


def test_find_ffmpeg_darwin_prefers_plain_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    tools = tmp_path / "tools"
    tools.mkdir()
    plain = tools / "ffmpeg"
    plain.write_text("fake")
    # Even if a Windows .exe is sitting next to it, darwin must pick the
    # plain (extensionless) binary first from APP_DIR/tools.
    (tools / "ffmpeg.exe").write_text("fake")
    monkeypatch.setattr(core, "APP_DIR", tmp_path)
    monkeypatch.setattr(core, "BASE_DIR", tmp_path / "elsewhere")
    assert core.find_ffmpeg({}) == str(plain)


def test_find_ffmpeg_win32_prefers_exe(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    tools = tmp_path / "tools"
    tools.mkdir()
    exe = tools / "ffmpeg.exe"
    exe.write_text("fake")
    (tools / "ffmpeg").write_text("fake")
    monkeypatch.setattr(core, "APP_DIR", tmp_path)
    monkeypatch.setattr(core, "BASE_DIR", tmp_path / "elsewhere")
    assert core.find_ffmpeg({}) == str(exe)


def test_find_soffice_darwin_tools_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    tools = tmp_path / "tools"
    tools.mkdir()
    plain = tools / "soffice"
    plain.write_text("fake")
    monkeypatch.setattr(core, "APP_DIR", tmp_path)
    monkeypatch.setattr(core, "BASE_DIR", tmp_path / "elsewhere")
    monkeypatch.setattr(core.shutil, "which", lambda name: None)
    assert core.find_soffice({}) == str(plain)


def test_find_soffice_darwin_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(core, "APP_DIR", tmp_path)
    monkeypatch.setattr(core, "BASE_DIR", tmp_path / "elsewhere")
    monkeypatch.setattr(core.shutil, "which", lambda name: None)
    # /Applications/LibreOffice.app does not exist on this Linux host and
    # no tools/soffice was created, so the darwin branch must give up
    # cleanly (the app then uses the HTML fallback and logs the guidance).
    if not Path("/Applications/LibreOffice.app/Contents/MacOS/soffice").exists():
        assert core.find_soffice({}) is None

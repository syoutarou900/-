# -*- coding: utf-8 -*-
"""Mac (darwin) retrofit tests.

These verify the darwin-only branches added for the macOS retrofit AND that
the pre-existing Windows behaviour is untouched:
- get_app_dir(): win32+APPDATA -> %APPDATA%\\ContextStruct (unchanged),
  win32 without APPDATA -> ~\\ContextStruct (unchanged fallback),
  darwin -> ~/Library/Application Support/ContextStruct (new).
- tesseract_path(): non-darwin resolves exactly like shutil.which;
  darwin falls back to the Homebrew locations in order.
- vlm_local.find_runtime_binary(): darwin never returns a Windows .exe;
  win32 still returns the first candidate present.
- vlm_local.download_runtime()/download_gpu_runtime(): darwin refuses the
  Windows-only downloads; the win32 code path is not entered here.
- i18n: ocr_missing_mac exists in all 13 languages; the original
  ocr_missing strings are unchanged.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import context_core
import vlm_local


def _with_platform(monkeypatch, value):
    monkeypatch.setattr(context_core.sys, "platform", value)
    monkeypatch.setattr(vlm_local.sys, "platform", value)


# ------------------------------------------------------------ get_app_dir ----
def test_app_dir_win32_with_appdata_unchanged(tmp_path, monkeypatch):
    _with_platform(monkeypatch, "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    # makedirs happens inside get_app_dir; point HOME at tmp so nothing
    # outside the sandbox is touched on the fallback path either.
    monkeypatch.setenv("HOME", str(tmp_path))
    d = context_core.get_app_dir()
    assert d == os.path.join(str(tmp_path / "appdata"), "ContextStruct")
    assert os.path.isdir(d)


def test_app_dir_win32_no_appdata_unchanged(tmp_path, monkeypatch):
    _with_platform(monkeypatch, "win32")
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path))
    d = context_core.get_app_dir()
    assert d == os.path.join(str(tmp_path), "ContextStruct")


def test_app_dir_darwin_uses_library_application_support(tmp_path, monkeypatch):
    _with_platform(monkeypatch, "darwin")
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path))
    d = context_core.get_app_dir()
    assert d == os.path.join(str(tmp_path), "Library", "Application Support", "ContextStruct")
    assert os.path.isdir(d)


def test_app_dir_linux_unchanged(tmp_path, monkeypatch):
    _with_platform(monkeypatch, "linux")
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path))
    d = context_core.get_app_dir()
    assert d == os.path.join(str(tmp_path), ".contextstruct")


def test_models_dir_follows_app_dir_on_darwin(tmp_path, monkeypatch):
    _with_platform(monkeypatch, "darwin")
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path))
    d = vlm_local.models_dir()
    assert d == os.path.join(str(tmp_path), "Library", "Application Support",
                             "ContextStruct", "models")


# ------------------------------------------------------------- tesseract ----
def test_tesseract_path_nondarwin_is_plain_which(monkeypatch):
    _with_platform(monkeypatch, "win32")
    monkeypatch.setattr(context_core.shutil, "which", lambda name: r"C:\tess\tesseract.exe")
    assert context_core.tesseract_path() == r"C:\tess\tesseract.exe"
    monkeypatch.setattr(context_core.shutil, "which", lambda name: None)
    assert context_core.tesseract_path() is None
    assert context_core.ocr_available() is False


def test_tesseract_path_darwin_prefers_path_then_homebrew(monkeypatch, tmp_path):
    _with_platform(monkeypatch, "darwin")
    # 1) PATH hit wins, exactly as before
    monkeypatch.setattr(context_core.shutil, "which", lambda name: "/usr/bin/tesseract")
    assert context_core.tesseract_path() == "/usr/bin/tesseract"
    # 2) no PATH hit -> first existing Homebrew candidate wins
    monkeypatch.setattr(context_core.shutil, "which", lambda name: None)
    brew = tmp_path / "brew"; brew.mkdir()
    fake = brew / "tesseract"; fake.write_text("#!/bin/sh\n"); fake.chmod(0o755)
    monkeypatch.setattr(context_core, "HOMEBREW_TESSERACT_CANDIDATES",
                        (str(fake), "/usr/local/bin/tesseract"))
    assert context_core.tesseract_path() == str(fake)
    assert context_core.ocr_available() is True
    # 3) nothing anywhere -> None
    monkeypatch.setattr(context_core, "HOMEBREW_TESSERACT_CANDIDATES",
                        ("/nonexistent-a/tesseract", "/nonexistent-b/tesseract"))
    assert context_core.tesseract_path() is None


# ------------------------------------------------------------ vlm runtime ----
def test_find_runtime_binary_darwin_skips_windows_exe(tmp_path, monkeypatch):
    _with_platform(monkeypatch, "darwin")
    (tmp_path / "llama-mtmd-cli.exe").write_bytes(b"MZ")
    assert vlm_local.find_runtime_binary(search_dirs=[str(tmp_path)]) is None
    # a manually placed macOS (extensionless) build IS picked up
    mac_bin = tmp_path / "llama-mtmd-cli"; mac_bin.write_bytes(b"\xcf\xfa")
    assert vlm_local.find_runtime_binary(search_dirs=[str(tmp_path)]) == str(mac_bin)


def test_find_runtime_binary_win32_unchanged(tmp_path, monkeypatch):
    _with_platform(monkeypatch, "win32")
    exe = tmp_path / "llama-mtmd-cli.exe"; exe.write_bytes(b"MZ")
    assert vlm_local.find_runtime_binary(search_dirs=[str(tmp_path)]) == str(exe)


def test_download_runtime_darwin_returns_none(monkeypatch):
    _with_platform(monkeypatch, "darwin")
    assert vlm_local.download_runtime() is None


def test_download_gpu_runtime_darwin_refused(monkeypatch):
    _with_platform(monkeypatch, "darwin")
    import pytest
    with pytest.raises(RuntimeError):
        vlm_local.download_gpu_runtime("vulkan")


# ------------------------------------------------------------------ i18n ----
def test_ocr_missing_mac_all_languages():
    from i18n_data import TRANSLATIONS, LANG_ORDER, t
    assert len(LANG_ORDER) == 13
    for code in LANG_ORDER:
        m = t(code, "ocr_missing_mac")
        assert m != "ocr_missing_mac", code
        assert "brew install tesseract" in m, code
        assert TRANSLATIONS[code]["ocr_missing_mac"] == m


def test_ocr_missing_original_strings_unchanged():
    # The Windows-facing message must still be the original wording.
    from i18n_data import t
    assert t("ja", "ocr_missing") == "OCR（Tesseract）が見つかりません。テキストを貼り付けるか手入力で直せます。Windowsでは Tesseract のインストールが必要です。"
    assert t("en", "ocr_missing") == "OCR (Tesseract) not found. Paste or type text manually. Tesseract must be installed on Windows."

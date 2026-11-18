# -*- coding: utf-8 -*-
"""プラットフォーム分岐（設定保存先）のテスト。

- darwin: ~/Library/Application Support/PurePaste（APPDATAがあっても優先）
- win32 + APPDATA: %APPDATA%\PurePaste（従来どおり）
- win32 で APPDATA 無し: ~/.purepaste（従来どおり）
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod


def test_config_dir_darwin(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "should_not_be_used"))
    path = appmod.config_dir()
    expected = os.path.join(str(tmp_path), "Library", "Application Support", "PurePaste")
    assert path == expected
    assert os.path.isdir(path)


def test_config_dir_win32_appdata(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    path = appmod.config_dir()
    assert path == os.path.join(str(tmp_path / "appdata"), "PurePaste")
    assert os.path.isdir(path)


def test_config_dir_win32_no_appdata(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("APPDATA", raising=False)
    path = appmod.config_dir()
    assert path == os.path.join(str(tmp_path), ".purepaste")
    assert os.path.isdir(path)

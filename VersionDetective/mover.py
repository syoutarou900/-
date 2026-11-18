# -*- coding: utf-8 -*-
"""Approved-only file moves to an archive folder, with undo.

Rules (semi-automatic principle):
- Nothing moves unless the user approved that exact item.
- Files are NEVER deleted and NEVER overwritten: a name clash in the
  destination gets an automatic serial suffix " (2)", " (3)", ...
- Every executed move is appended to a persistent JSON log in the app
  data folder, so undo works even after an app restart.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime

from appinfo import APP_ID


def data_dir() -> str:
    if sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library",
                            "Application Support")
    elif sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get(
            "XDG_DATA_HOME",
            os.path.join(os.path.expanduser("~"), ".local", "share"))
    path = os.path.join(base, APP_ID)
    os.makedirs(path, exist_ok=True)
    return path


def settings_path() -> str:
    return os.path.join(data_dir(), "settings.json")


def log_path() -> str:
    return os.path.join(data_dir(), "move_log.json")


def load_settings() -> dict:
    try:
        with open(settings_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    with open(settings_path(), "w", encoding="utf-8") as fh:
        json.dump(settings, fh, ensure_ascii=False, indent=1)


def load_log() -> list:
    try:
        with open(log_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save_log(entries: list) -> None:
    with open(log_path(), "w", encoding="utf-8") as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=1)


def unique_destination(dst_dir: str, filename: str) -> str:
    """Collision-free destination path: appends ' (2)', ' (3)', ...
    before the extension instead of overwriting."""
    candidate = os.path.join(dst_dir, filename)
    if not os.path.exists(candidate):
        return candidate
    stem, ext = os.path.splitext(filename)
    n = 2
    while True:
        candidate = os.path.join(dst_dir, f"{stem} ({n}){ext}")
        if not os.path.exists(candidate):
            return candidate
        n += 1


def execute_moves(moves):
    """Execute approved moves: list of (src_path, dst_dir).

    Returns (done, errors).  Successful moves are appended to the
    persistent log at once, all sharing one batch id.
    """
    entries = load_log()
    batch = datetime.now().strftime("%Y%m%d%H%M%S%f")
    done, errors = [], []
    for src, dst_dir in moves:
        try:
            os.makedirs(dst_dir, exist_ok=True)
            dst = unique_destination(dst_dir, os.path.basename(src))
            shutil.move(src, dst)
            entry = {"time": datetime.now().isoformat(timespec="seconds"),
                     "batch": batch, "src": src, "dst": dst,
                     "undone": False}
            entries.append(entry)
            done.append(entry)
        except (OSError, shutil.Error) as exc:
            errors.append((src, str(exc)))
    if done:
        _save_log(entries)
    return done, errors


def undo_last_batch():
    """Reverse the newest not-yet-undone batch of moves.

    Returns (done, errors).  If the original location is occupied
    again, the returned file gets a serial suffix rather than
    overwriting anything.
    """
    entries = load_log()
    live = [e for e in entries if not e.get("undone")]
    if not live:
        return [], []
    batch = live[-1].get("batch")
    targets = [e for e in live if e.get("batch") == batch]
    done, errors = [], []
    for entry in reversed(targets):
        src_now, back_to = entry["dst"], entry["src"]
        try:
            parent = os.path.dirname(back_to)
            if parent:
                os.makedirs(parent, exist_ok=True)
            dst = back_to
            if os.path.exists(dst) and os.path.abspath(dst) != \
                    os.path.abspath(src_now):
                dst = unique_destination(parent or ".",
                                         os.path.basename(back_to))
            shutil.move(src_now, dst)
            entry["undone"] = True
            entry["undo_dst"] = dst
            done.append(entry)
        except (OSError, shutil.Error) as exc:
            errors.append((src_now, str(exc)))
    _save_log(entries)
    return done, errors

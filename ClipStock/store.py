# -*- coding: utf-8 -*-
"""
ClipStock - history store (pure logic, no Qt dependency).

Holds copied items grouped into "work sets":
- A new set starts automatically when the gap since the previous copy is
  at least `gap_seconds` (default 1800 = 30 minutes).
- The user can also start a new set manually at any time.
- Set names are generated from the start date/time and can be renamed.

Items can be pinned; pinned items are exempt from automatic expiry.
Expiry removes unpinned items older than the configured TTL.
The store persists to a local JSON file only (no network, ever).
"""
import json
import os
import time
import uuid

DEFAULT_GAP_SECONDS = 1800


def _new_id():
    return uuid.uuid4().hex[:12]


class Store:
    def __init__(self, gap_seconds=DEFAULT_GAP_SECONDS):
        self.gap_seconds = gap_seconds
        self.items = []          # list of dicts, oldest first
        self.sets = []           # list of dicts {id, name, created}
        self.current_set_id = None
        self._last_ts = None

    # ---------- sets ----------
    def _auto_set_name(self, ts):
        lt = time.localtime(ts)
        return time.strftime("%Y-%m-%d %H:%M", lt)

    def start_set(self, ts=None, name=None):
        ts = time.time() if ts is None else ts
        s = {"id": _new_id(), "name": name or self._auto_set_name(ts),
             "created": ts}
        self.sets.append(s)
        self.current_set_id = s["id"]
        return s

    def rename_set(self, set_id, name):
        for s in self.sets:
            if s["id"] == set_id:
                s["name"] = name
                return True
        return False

    def get_set(self, set_id):
        for s in self.sets:
            if s["id"] == set_id:
                return s
        return None

    def _ensure_set_for(self, ts):
        if self.current_set_id is None or self.get_set(self.current_set_id) is None:
            return self.start_set(ts)
        if self._last_ts is not None and ts - self._last_ts >= self.gap_seconds:
            return self.start_set(ts)
        return self.get_set(self.current_set_id)

    # ---------- items ----------
    def add(self, text, kind, reason, ts=None):
        """Add a copied text. Consecutive duplicates are not stored twice.
        Returns the item dict, or None when skipped as a duplicate."""
        ts = time.time() if ts is None else ts
        if self.items and self.items[-1]["text"] == text:
            self._last_ts = ts
            return None
        workset = self._ensure_set_for(ts)
        item = {"id": _new_id(), "text": text, "kind": kind,
                "reason": reason, "ts": ts, "pinned": False,
                "set_id": workset["id"]}
        self.items.append(item)
        self._last_ts = ts
        return item

    def delete_item(self, item_id):
        before = len(self.items)
        self.items = [i for i in self.items if i["id"] != item_id]
        return len(self.items) != before

    def set_pinned(self, item_id, pinned):
        for i in self.items:
            if i["id"] == item_id:
                i["pinned"] = bool(pinned)
                return True
        return False

    def clear_all(self):
        self.items = []
        self.sets = []
        self.current_set_id = None
        self._last_ts = None

    def expire(self, ttl_seconds, now=None):
        """Remove unpinned items older than ttl_seconds.
        ttl_seconds=None means 'never expire'. Returns removed count.
        Sets that become empty (and are not current) are dropped."""
        if ttl_seconds is None:
            return 0
        now = time.time() if now is None else now
        cutoff = now - ttl_seconds
        before = len(self.items)
        self.items = [i for i in self.items
                      if i["pinned"] or i["ts"] >= cutoff]
        removed = before - len(self.items)
        used = {i["set_id"] for i in self.items}
        self.sets = [s for s in self.sets
                     if s["id"] in used or s["id"] == self.current_set_id]
        return removed

    def items_in_set(self, set_id):
        return [i for i in self.items if i["set_id"] == set_id]

    # ---------- persistence ----------
    def to_dict(self):
        return {"items": self.items, "sets": self.sets,
                "current_set_id": self.current_set_id,
                "last_ts": self._last_ts}

    @classmethod
    def from_dict(cls, data, gap_seconds=DEFAULT_GAP_SECONDS):
        st = cls(gap_seconds=gap_seconds)
        if isinstance(data, dict):
            st.items = [i for i in data.get("items", []) if isinstance(i, dict)]
            st.sets = [s for s in data.get("sets", []) if isinstance(s, dict)]
            st.current_set_id = data.get("current_set_id")
            st._last_ts = data.get("last_ts")
        return st

    def save(self, path):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path, gap_seconds=DEFAULT_GAP_SECONDS):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        return cls.from_dict(data, gap_seconds=gap_seconds)

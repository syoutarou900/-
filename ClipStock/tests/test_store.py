# -*- coding: utf-8 -*-
"""Tests for the history store: sets, dedup, pin, expiry, persistence."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from store import Store

T0 = 1_700_000_000.0


def test_first_add_creates_set():
    st = Store()
    item = st.add("https://example.com", "url", "url", ts=T0)
    assert item is not None
    assert len(st.sets) == 1
    assert item["set_id"] == st.sets[0]["id"]
    assert st.current_set_id == st.sets[0]["id"]


def test_consecutive_duplicate_skipped():
    st = Store()
    st.add("abc", "other", "other", ts=T0)
    assert st.add("abc", "other", "other", ts=T0 + 10) is None
    assert len(st.items) == 1


def test_nonconsecutive_duplicate_kept():
    st = Store()
    st.add("abc", "other", "other", ts=T0)
    st.add("xyz", "other", "other", ts=T0 + 10)
    assert st.add("abc", "other", "other", ts=T0 + 20) is not None
    assert len(st.items) == 3


def test_gap_starts_new_set():
    st = Store(gap_seconds=1800)
    st.add("a", "other", "other", ts=T0)
    st.add("b", "other", "other", ts=T0 + 1799)
    assert len(st.sets) == 1
    st.add("c", "other", "other", ts=T0 + 1799 + 1800)
    assert len(st.sets) == 2
    assert st.items[-1]["set_id"] == st.sets[1]["id"]


def test_manual_set_and_rename():
    st = Store()
    st.add("a", "other", "other", ts=T0)
    s2 = st.start_set(ts=T0 + 60, name="午後の作業")
    assert s2["name"] == "午後の作業"
    st.add("b", "other", "other", ts=T0 + 70)
    assert st.items[-1]["set_id"] == s2["id"]
    assert st.rename_set(s2["id"], "請求書の転記") is True
    assert st.get_set(s2["id"])["name"] == "請求書の転記"
    assert st.rename_set("missing", "x") is False


def test_auto_set_name_is_datetime():
    st = Store()
    s = st.start_set(ts=T0)
    assert len(s["name"]) == 16 and s["name"][4] == "-"


def test_delete_and_pin():
    st = Store()
    a = st.add("a", "other", "other", ts=T0)
    b = st.add("b", "other", "other", ts=T0 + 1)
    assert st.set_pinned(a["id"], True) is True
    assert st.items[0]["pinned"] is True
    assert st.delete_item(b["id"]) is True
    assert len(st.items) == 1
    assert st.delete_item("missing") is False


def test_expire_removes_old_unpinned_only():
    st = Store()
    old = st.add("old", "other", "other", ts=T0)
    pinned = st.add("keep", "other", "other", ts=T0 + 1)
    st.set_pinned(pinned["id"], True)
    st.add("new", "other", "other", ts=T0 + 100000)
    removed = st.expire(ttl_seconds=3600, now=T0 + 100000)
    assert removed == 1
    texts = [i["text"] for i in st.items]
    assert texts == ["keep", "new"]
    assert old["id"] not in [i["id"] for i in st.items]


def test_expire_none_means_never():
    st = Store()
    st.add("a", "other", "other", ts=T0)
    assert st.expire(ttl_seconds=None, now=T0 + 10**9) == 0
    assert len(st.items) == 1


def test_expire_drops_empty_sets():
    st = Store(gap_seconds=60)
    st.add("a", "other", "other", ts=T0)
    st.add("b", "other", "other", ts=T0 + 3600)
    assert len(st.sets) == 2
    st.expire(ttl_seconds=60, now=T0 + 3600)
    assert len(st.sets) == 1  # first set became empty and was dropped


def test_clear_all():
    st = Store()
    st.add("a", "other", "other", ts=T0)
    st.clear_all()
    assert st.items == [] and st.sets == [] and st.current_set_id is None


def test_save_load_roundtrip():
    st = Store(gap_seconds=900)
    st.add("https://example.com", "url", "url", ts=T0)
    st.add("¥100", "amount", "amount_symbol", ts=T0 + 5)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "history.json")
        st.save(path)
        st2 = Store.load(path, gap_seconds=900)
    assert [i["text"] for i in st2.items] == ["https://example.com", "¥100"]
    assert st2.current_set_id == st.current_set_id
    assert len(st2.sets) == 1


def test_load_missing_file_is_empty():
    st = Store.load("/nonexistent/dir/history.json")
    assert st.items == [] and st.sets == []

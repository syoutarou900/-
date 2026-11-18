# -*- coding: utf-8 -*-
"""All 13 languages must carry every key, with no empty strings."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from i18n_data import LANG_ORDER, TRANSLATIONS, t


def test_all_languages_present():
    assert list(TRANSLATIONS.keys()) == LANG_ORDER
    assert len(LANG_ORDER) == 13


def test_all_keys_everywhere():
    base = set(TRANSLATIONS["ja"].keys())
    assert len(base) >= 60
    for lang in LANG_ORDER:
        keys = set(TRANSLATIONS[lang].keys())
        assert keys == base, (lang, base ^ keys)


def test_no_empty_strings():
    for lang in LANG_ORDER:
        for key, val in TRANSLATIONS[lang].items():
            assert isinstance(val, str) and val.strip(), (lang, key)


def test_format_placeholders():
    for lang in LANG_ORDER:
        out = t(lang, "count_fmt", count=5)
        assert "5" in out, lang


def test_fallback():
    assert t("xx", "tab_all") == TRANSLATIONS["ja"]["tab_all"]
    assert t("ja", "no_such_key") == "no_such_key"

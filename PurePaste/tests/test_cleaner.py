# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from cleaner import clean_text, DEFAULT_SETTINGS

def test_pdf_japanese_join():
    src = "本日は晴天\nなり。明日も\n晴れるでしょう。\n\n次の段落です。"
    assert clean_text(src) == "本日は晴天なり。明日も晴れるでしょう。\n\n次の段落です。"

def test_english_wrap_join_with_space():
    assert clean_text("The quick brown\nfox jumps over.") == "The quick brown fox jumps over."

def test_hyphenation():
    assert clean_text("informa-\ntion is here") == "information is here"

def test_fullwidth_alnum():
    assert clean_text("Ｔｅｓｔ１２３　ＡＢＣ") == "Test123 ABC"

def test_japanese_spaces_removed():
    assert clean_text("こ ん に ち は　世 界") == "こんにちは世界"

def test_halfwidth_kana():
    # 半角カナ→全角化され、日本語同士の間のスペースは除去される
    assert clean_text("ｱｲｳｴｵ ｶﾞｷﾞ") == "アイウエオガギ"

def test_collapse_spaces_and_tabs():
    assert clean_text("a    b\t\tc") == "a b c"

def test_blank_lines():
    assert clean_text("a\n\n\n\nb") == "a\n\nb"

def test_list_lines_preserved():
    src = "買い物リスト\n・りんご\n・バナナ"
    out = clean_text(src)
    assert "・りんご\n・バナナ" in out

def test_no_join_when_disabled():
    s = dict(DEFAULT_SETTINGS); s["join_lines"] = False
    assert clean_text("本日は\n晴天です", s) == "本日は\n晴天です"

def test_fullwidth_kept_when_disabled():
    s = dict(DEFAULT_SETTINGS); s["fullwidth_alnum_half"] = False
    assert clean_text("Ｔｅｓｔ", s) == "Ｔｅｓｔ"

def test_url_join():
    src = "https://example.com/very/long/\npath/page.html"
    assert clean_text(src) == "https://example.com/very/long/path/page.html"

def test_nbsp_and_zero_width():
    assert clean_text("a\xa0b\u200bc") == "a bc"

def test_idempotent():
    samples = [
        "本日は晴天\nなり。明日も\n晴れるでしょう。",
        "Ｔｅｓｔ１２３ ｱｲｳ こ ん に ち は",
        "The quick brown\nfox\n\n\njumps.",
    ]
    for x in samples:
        once = clean_text(x)
        assert clean_text(once) == once

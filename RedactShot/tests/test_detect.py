# -*- coding: utf-8 -*-
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import detect


ALL = set(detect.CATEGORIES)


def word(text, x=0, y=0, w=None, h=20, line=0):
    if w is None:
        w = max(10, len(text) * 10)
    return {"text": text, "x": x, "y": y, "w": w, "h": h, "line": line}


def line_words(texts, y=0, line=0, x0=0):
    words = []
    x = x0
    for t in texts:
        w = max(10, len(t) * 10)
        words.append(word(t, x=x, y=y, w=w, line=line))
        x += w + 10
    return words


def run(words, custom=None, enabled=None, img_w=1000, img_h=200):
    return detect.detect(words, img_w, img_h, custom or [], ALL if enabled is None else enabled)


def by_cat(cands, cat):
    return [c for c in cands if c.category == cat]


# --- normalize / luhn -------------------------------------------------------

def test_normalize_fullwidth_and_case():
    assert detect.normalize("ＡＢＣ１２３") == "abc123"
    assert detect.normalize("AbC") == "abc"


def test_luhn_pass():
    assert detect.luhn_ok("4111111111111111") is True


def test_luhn_fail():
    assert detect.luhn_ok("4111111111111112") is False


def test_luhn_rejects_non_digits():
    assert detect.luhn_ok("") is False
    assert detect.luhn_ok("4111abcd") is False


# --- card -------------------------------------------------------------------

def test_card_luhn_pass_reason():
    cands = run(line_words(["4111111111111111"]))
    cards = by_cat(cands, "card")
    assert len(cards) == 1
    assert cards[0].reason_key == "card_luhn_pass"
    assert cards[0].reason_params == {"digits": 16}


def test_card_luhn_fail_reason():
    cands = run(line_words(["4111111111111112"]))
    cards = by_cat(cands, "card")
    assert len(cards) == 1
    assert cards[0].reason_key == "card_luhn_fail"
    assert cards[0].reason_params == {"digits": 16}


def test_card_with_spaces():
    cands = run(line_words(["4111", "1111", "1111", "1111"]))
    cards = by_cat(cands, "card")
    assert len(cards) == 1
    assert cards[0].reason_params == {"digits": 16}


# --- phone ------------------------------------------------------------------

def test_phone_jp_hyphen():
    cands = run(line_words(["03-1234-5678"]))
    phones = by_cat(cands, "phone")
    assert len(phones) == 1
    assert phones[0].reason_key == "phone_pattern"
    # 10 digits must not be misreported as a card.
    assert by_cat(cands, "card") == []


def test_phone_continuous():
    cands = run(line_words(["09012345678"]))
    phones = by_cat(cands, "phone")
    assert len(phones) == 1
    assert by_cat(cands, "card") == []


def test_phone_continuous_not_part_of_longer_digits():
    # 12-digit sequence starting with 0: the 10/11-digit phone must not
    # be carved out of a longer digit string.
    cands = run(line_words(["090123456789"]))
    assert by_cat(cands, "phone") == []


def test_phone_international():
    cands = run(line_words(["+81", "90-1234-5678"]))
    phones = by_cat(cands, "phone")
    assert len(phones) == 1
    assert phones[0].text.startswith("+81")


# --- email ------------------------------------------------------------------

def test_email():
    cands = run(line_words(["taro@example.co.jp"]))
    emails = by_cat(cands, "email")
    assert len(emails) == 1
    assert emails[0].reason_key == "email_pattern"
    assert emails[0].text == "taro@example.co.jp"


def test_email_split_across_words_no_false_positive():
    # A bare "@" separated by spaces is not an email pattern.
    cands = run(line_words(["taro", "@", "example"]))
    assert by_cat(cands, "email") == []


# --- money ------------------------------------------------------------------

def test_money_yen_symbol():
    cands = run(line_words(["¥12,345"]))
    money = by_cat(cands, "money")
    assert len(money) == 1
    assert money[0].reason_key == "money_pattern"


def test_money_dollar():
    cands = run(line_words(["$99.99"]))
    money = by_cat(cands, "money")
    assert len(money) == 1


def test_money_yen_suffix():
    cands = run(line_words(["500円"]))
    money = by_cat(cands, "money")
    assert len(money) == 1


def test_money_plain_number_is_not_money():
    cands = run(line_words(["12345"]))
    assert by_cat(cands, "money") == []


# --- masked -----------------------------------------------------------------

def test_masked():
    cands = run(line_words(["●●●●●●"]))
    masked = by_cat(cands, "masked")
    assert len(masked) == 1
    assert masked[0].reason_key == "mask_chars"


def test_masked_too_short():
    cands = run(line_words(["●●"]))
    assert by_cat(cands, "masked") == []


# --- password ---------------------------------------------------------------

def test_password_label_with_right_word():
    words = [
        word("パスワード", x=0, y=0, w=80, h=20, line=0),
        word("secret123", x=100, y=0, w=90, h=20, line=0),
    ]
    cands = run(words)
    pw = by_cat(cands, "password")
    assert len(pw) == 1
    assert pw[0].reason_key == "password_estimate"
    # Candidate covers the word to the right of the label.
    assert pw[0].x <= 100
    assert pw[0].x + pw[0].w >= 190
    assert pw[0].y <= 0 + 20 and pw[0].y + pw[0].h >= 0


def test_password_label_alone_estimates_box_to_the_right():
    words = [word("password:", x=0, y=10, w=80, h=20, line=0)]
    cands = run(words, img_w=1000, img_h=200)
    pw = by_cat(cands, "password")
    assert len(pw) == 1
    # Estimated box starts at the right edge of the label and is wide.
    assert pw[0].x == 80
    assert pw[0].w == max(160, 80 * 3)


def test_password_label_alone_near_right_edge_goes_below():
    words = [word("password", x=970, y=10, w=20, h=20, line=0)]
    cands = run(words, img_w=1000, img_h=200)
    pw = by_cat(cands, "password")
    assert len(pw) == 1
    # Less than 40px remains to the right, so the box goes below.
    assert pw[0].y == 30
    assert pw[0].x == 970


def test_password_non_label_word_not_detected():
    cands = run(line_words(["passwords"]))
    assert by_cat(cands, "password") == []


# --- custom -----------------------------------------------------------------

def test_custom_exact_match():
    cands = run(line_words(["社外秘"]), custom=["社外秘"])
    custom = by_cat(cands, "custom")
    assert len(custom) == 1
    assert custom[0].reason_key == "custom_term"


def test_custom_normalization_fullwidth_and_case():
    # Fullwidth -> halfwidth and case differences still match.
    cands = run(line_words(["ＣＯＮＦＩＤＥＮＴＩＡＬ"]), custom=["Confidential"])
    assert len(by_cat(cands, "custom")) == 1
    cands2 = run(line_words(["confidential"]), custom=["ＣＯＮＦＩＤＥＮＴＩＡＬ"])
    assert len(by_cat(cands2, "custom")) == 1


def test_custom_no_match_when_term_differs_after_normalization():
    # After normalisation the strings still differ -> no detection.
    cands = run(line_words(["ABC124"]), custom=["ABC123"])
    assert by_cat(cands, "custom") == []
    cands2 = run(line_words(["社外"]), custom=["社外秘"])
    assert by_cat(cands2, "custom") == []
    # A shorter fragment of the registered term is not a match.
    cands3 = run(line_words(["confident"]), custom=["Confidential"])
    assert by_cat(cands3, "custom") == []


def test_custom_substring_inside_word_is_detected_per_spec():
    # Spec: substring exact match inside a word counts as a detection.
    cands = run(line_words(["xxSECRETxx"]), custom=["SECRET"])
    assert len(by_cat(cands, "custom")) == 1


# --- enabled / categories ---------------------------------------------------

def test_disabled_category_not_detected():
    words = line_words(["taro@example.co.jp"])
    cands = run(words, enabled={"phone", "card"})
    assert by_cat(cands, "email") == []
    cands_all = run(words, enabled=ALL)
    assert len(by_cat(cands_all, "email")) == 1


def test_disabled_custom_not_detected():
    words = line_words(["社外秘"])
    cands = run(words, custom=["社外秘"], enabled=set(ALL) - {"custom"})
    assert by_cat(cands, "custom") == []


def test_candidate_fields_and_defaults():
    cands = run(line_words(["taro@example.co.jp"]))
    c = by_cat(cands, "email")[0]
    assert isinstance(c.id, int)
    assert c.enabled is True
    assert c.manual is False
    assert c.w > 0 and c.h > 0


def test_duplicate_candidates_merged():
    # Same phone written in a way matched by two phone patterns must
    # collapse to a single candidate for the same range/category.
    cands = run(line_words(["090-1234-5678"]))
    phones = by_cat(cands, "phone")
    assert len(phones) == 1


def test_password_stacked_layout_prefers_below():
    # Label alone on its line; a word sits just below under the label
    # (stacked login form) -> candidate must be below and cover that word.
    words = [
        {"text": "パスワード", "x": 400, "y": 470, "w": 126, "h": 22, "line": 0},
        {"text": "xxxxxxxx", "x": 420, "y": 532, "w": 240, "h": 27, "line": 1},
    ]
    cands = [c for c in detect.detect(words, 1600, 1000, [], ALL)
             if c.category == "password"]
    assert len(cands) == 1
    c = cands[0]
    assert c.y >= 492  # below the label
    # overlaps the field area (400,505,800,70)
    assert c.x < 1200 and c.x + c.w > 400 and c.y < 575 and c.y + c.h > 505


def test_password_no_below_evidence_keeps_right_estimate():
    words = [
        {"text": "パスワード", "x": 100, "y": 100, "w": 126, "h": 22, "line": 0},
    ]
    cands = [c for c in detect.detect(words, 1600, 1000, [], ALL)
             if c.category == "password"]
    assert len(cands) == 1
    assert cands[0].x >= 226  # right of the label, as before

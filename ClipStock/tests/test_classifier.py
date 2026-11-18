# -*- coding: utf-8 -*-
"""Tests for the deterministic classifier and the sensitive-shape check."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from classifier import classify, is_sensitive, luhn_ok


def kind(text):
    return classify(text)[0]


def reason(text):
    return classify(text)[1]


# ---------- URL ----------
def test_url_http():
    assert kind("https://example.com/path?q=1") == "url"
    assert reason("https://example.com") == "url"


def test_url_www():
    assert kind("www.example.co.jp/item/123") == "url"


def test_url_beats_email_like():
    # Contains '@' but starts with a scheme: URL is checked first.
    assert kind("https://user@example.com/x") == "url"


# ---------- Email ----------
def test_email():
    assert kind("taro.yamada+tag@example.co.jp") == "email"
    assert reason("a@b.com") == "email"


def test_email_needs_tld():
    assert kind("taro@localhost") != "email"


# ---------- Amount ----------
def test_amount_symbol():
    assert kind("¥12,800") == "amount"
    assert reason("¥12,800") == "amount_symbol"
    assert kind("$1,234.56") == "amount"
    assert kind("€99") == "amount"


def test_amount_unit():
    assert kind("12,800円") == "amount"
    assert reason("500 USD") == "amount_unit"
    assert kind("3,000ウォン") == "amount"


def test_amount_thousands():
    assert kind("1,234,567") == "amount"
    assert reason("12,345") == "amount_thousands"


def test_plain_small_number_is_not_amount():
    # A bare number without separators/symbol/unit stays 'other'
    # (it may be a quantity, a page number, anything).
    assert kind("42") == "other"
    assert kind("2026") == "other"


# ---------- Date ----------
def test_date_iso():
    assert kind("2026-11-17") == "date"
    assert kind("2026/1/5") == "date"


def test_date_japanese():
    assert kind("2026年11月17日") == "date"


def test_date_dmy():
    assert kind("17/11/2026") == "date"
    assert kind("03-04-2026") == "date"


def test_datetime_and_time():
    assert kind("2026-11-17 09:30") == "date"
    assert kind("09:30") == "date"
    assert reason("09:30:15") == "time"


def test_date_beats_code():
    # A date-shaped string must not fall into the digit-code rule.
    assert kind("2026-11-17") == "date"


# ---------- Address ----------
def test_address_japanese():
    assert kind("愛知県名古屋市中村区名駅1丁目1-1") == "address"
    assert reason("東京都新宿区西新宿2-8-1") == "address_jp"


def test_address_japanese_postal():
    assert kind("〒450-0002 愛知県名古屋市中村区名駅1-1") == "address"


def test_address_english():
    assert kind("1600 Amphitheatre Parkway") != "address"  # no street suffix
    assert kind("350 Fifth Avenue") == "address"
    assert reason("12 Main Street") == "address_en"


def test_address_needs_number():
    # Street word alone without a number is not an address.
    assert kind("Main Street") != "address"


# ---------- Code ----------
def test_code_mixed():
    assert kind("ABC-1234") == "code"
    assert reason("SKU_9982-X") == "code_mixed"
    assert kind("AB12CD") == "code"


def test_code_digits():
    assert kind("4901234567890") == "code"      # JAN-like 13 digits
    assert kind("090-1234-5678") == "code"      # digit sequence w/ hyphens
    assert reason("4901234") == "code_digits"


def test_code_needs_letter_and_digit():
    assert kind("HELLO") != "code"   # letters only
    assert kind("hello-world") != "code"


# ---------- Other / shape guards ----------
def test_multiline_is_other():
    assert kind("一行目\n二行目") == "other"
    assert reason("a\nb") == "multiline"


def test_long_text_is_other():
    assert kind("あ" * 600) == "other"
    assert reason("x" * 501) == "long"


def test_plain_words_other():
    assert kind("こんにちは") == "other"
    assert kind("会議室A") == "other"  # letter+digit but has non-ASCII char
    assert kind("") == "other"
    assert kind("   ") == "other"
    assert kind(None) == "other"


def test_amount_beats_code_for_thousands():
    # '1,234' has digits and a comma: amount rule runs before code.
    assert kind("1,234") == "amount"


# ---------- Sensitive shapes ----------
def test_luhn():
    assert luhn_ok("4111111111111111") is True    # Visa test number
    assert luhn_ok("4111111111111112") is False
    assert luhn_ok("") is False
    assert luhn_ok("abcd") is False


def test_sensitive_card():
    assert is_sensitive("4111 1111 1111 1111") == "card"
    assert is_sensitive("4111-1111-1111-1111") == "card"
    assert is_sensitive("4111111111111111") == "card"


def test_sensitive_not_card_when_luhn_fails():
    assert is_sensitive("4111 1111 1111 1112") is None
    assert is_sensitive("1234 5678 9012 3456") is None


def test_sensitive_label():
    assert is_sensitive("password: hunter2") == "secret_label"
    assert is_sensitive("パスワード：abc123") == "secret_label"


def test_sensitive_normal_text():
    assert is_sensitive("https://example.com") is None
    assert is_sensitive("普通の文章です") is None
    assert is_sensitive(None) is None

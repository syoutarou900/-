# -*- coding: utf-8 -*-
"""
テキスト整形ロジック（Qtに依存しない純Python）

WebサイトやPDFからコピーしたテキストの
- 変な改行（行の途中で切れた改行）
- 不必要なスペース（連続スペース、タブ、日本語の間のスペース）
- 全角・半角の混在（全角英数字、半角カナ、全角スペース）
を整える。
"""
import re
import unicodedata

DEFAULT_SETTINGS = {
    "enabled": True,               # 自動整形 ON/OFF
    "join_lines": True,            # 変な改行を取って文をつなげる
    "collapse_spaces": True,       # 連続スペース・タブを1つに
    "trim_lines": True,            # 行頭・行末のスペースを取る
    "fullwidth_alnum_half": True,  # 全角英数字 → 半角
    "halfwidth_kana_full": True,   # 半角カナ → 全角カナ
    "fullwidth_space_half": True,  # 全角スペース → 半角スペース
    "remove_jp_spaces": True,      # 日本語の間に入ったスペースを取る
    "collapse_blank_lines": True,  # 3行以上の空行を1行に
    "notify": False,               # 整形したときに通知する
    "autostart": False,            # Windows起動時に自動開始（app側で処理）
}

# 日本語文字（ひらがな・カタカナ・漢字・和文記号）
_JP = r"\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3000-\u303f\uff01-\uff0f\uff1a-\uff20\uff3b-\uff40\uff5b-\uff65"
_JP_RE_BOTH = re.compile(r"(?<=[%s])[ \t]+(?=[%s])" % (_JP, _JP))
# 英単語の途中でハイフン＋改行された場合
_HYPHEN_BREAK = re.compile(r"([A-Za-z])-\s*\n\s*(?=[a-z])")
# URL / メールっぽい行の判定
_URL_LIKE = re.compile(r"(https?://|www\.|[\w.+-]+@[\w-]+\.[\w.]+)", re.I)
# 箇条書きの行頭
_LIST_HEAD = re.compile(r"^\s*(?:[・•·\-*＊※>]|[0-9０-９]+[\.．、\)）]|[①-⑳]|[（\(][0-9０-９]+[）\)])\s*")

_FULLWIDTH_ALNUM = {}
for _i in range(0xFF01, 0xFF5F):
    pass
_ALNUM_TABLE = {}
for _c in "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ０１２３４５６７８９":
    _ALNUM_TABLE[ord(_c)] = chr(ord(_c) - 0xFEE0)

_HALFWIDTH_KANA = re.compile(r"[\uff61-\uff9f]+")


def _halfwidth_kana_to_full(text):
    def repl(m):
        return unicodedata.normalize("NFKC", m.group(0))
    return _HALFWIDTH_KANA.sub(repl, text)


def _is_jp_char(ch):
    if not ch:
        return False
    o = ord(ch)
    return (
        0x3040 <= o <= 0x30FF
        or 0x3400 <= o <= 0x4DBF
        or 0x4E00 <= o <= 0x9FFF
        or 0x3000 <= o <= 0x303F
        or o in (0x30FC,)  # ー
    )


def _needs_space_between(left, right):
    """行をつなげるとき、間に半角スペースが要るかどうか"""
    if not left or not right:
        return False
    l, r = left[-1], right[0]
    # 日本語が絡む場合はスペース不要
    if _is_jp_char(l) or _is_jp_char(r):
        return False
    # 英数字同士はスペースが要る
    if (l.isalnum() or l in ".,") and (r.isalnum()):
        return True
    return False


def _join_paragraph_lines(lines):
    """段落内の行を、意味のある改行だけ残してつなげる"""
    out = []
    buf = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if not buf:
            buf = line
            continue
        # 次の行が箇条書きなら改行を残す
        if _LIST_HEAD.match(line):
            out.append(buf)
            buf = line
            continue
        # 前の行が「：」「:」で終わる（見出し＋本文の形）なら改行を残す
        if buf.rstrip().endswith((":", "：")):
            out.append(buf)
            buf = line
            continue
        # つなげる
        if buf.endswith("-") and len(buf) >= 2 and buf[-2].isalpha() and line[0].islower():
            # 英単語のハイフン改行 → ハイフンを取って直結
            buf = buf[:-1] + line
        elif _URL_LIKE.search(buf) and " " not in buf.strip():
            # URLが途中で切れている場合は直結
            buf = buf + line
        elif _needs_space_between(buf, line):
            buf = buf + " " + line
        else:
            buf = buf + line
    if buf:
        out.append(buf)
    return "\n".join(out)


def clean_text(text, settings=None):
    """テキストを整形して返す。settings は DEFAULT_SETTINGS のキーの辞書。"""
    if text is None:
        return ""
    s = dict(DEFAULT_SETTINGS)
    if settings:
        s.update({k: v for k, v in settings.items() if k in DEFAULT_SETTINGS})

    t = str(text)
    # 改行コードを統一し、見えない文字を取り除く
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\ufeff", "")
    t = t.replace("\xa0", " ")  # ノーブレークスペース
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t)

    if s["halfwidth_kana_full"]:
        t = _halfwidth_kana_to_full(t)
    if s["fullwidth_alnum_half"]:
        t = t.translate(_ALNUM_TABLE)
    if s["fullwidth_space_half"]:
        t = t.replace("\u3000", " ")

    # 段落（空行で区切られた塊）ごとに処理する
    paragraphs = re.split(r"\n[ \t]*\n", t)
    cleaned_paras = []
    for para in paragraphs:
        lines = para.split("\n")
        proc_lines = []
        for line in lines:
            if s["collapse_spaces"]:
                line = re.sub(r"[ \t]+", " ", line)
            if s["trim_lines"]:
                line = line.strip()
            proc_lines.append(line)
        # 段落の前後の空行は落とす
        while proc_lines and proc_lines[0] == "":
            proc_lines.pop(0)
        while proc_lines and proc_lines[-1] == "":
            proc_lines.pop()
        if not proc_lines:
            continue
        if s["join_lines"]:
            joined = _join_paragraph_lines(proc_lines)
        else:
            joined = "\n".join(proc_lines)
        cleaned_paras.append(joined)

    t = "\n\n".join(cleaned_paras)

    if s["remove_jp_spaces"]:
        # 日本語と日本語の間に入ったスペースを取る（PDFコピーで多い）
        t = _JP_RE_BOTH.sub("", t)
        # 日本語の句読点の前後のスペースを取る
        t = re.sub(r"[ ]+(?=[、。．，！？：；])", "", t)
        t = re.sub(r"(?<=[、。．，！？：；])[ ]+(?=[%s])" % _JP, "", t)

    if s["collapse_spaces"]:
        t = re.sub(r"[ \t]{2,}", " ", t)
    if s["collapse_blank_lines"]:
        t = re.sub(r"\n{3,}", "\n\n", t)

    return t.strip()

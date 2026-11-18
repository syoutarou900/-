バージョン探偵 / VersionDetective
================================================

「最終版」「最終版2」「提出用_修正」「本当の最終版」…。
共有フォルダに似た名前の版が並んだとき、どれが本当の最新かを
ファイル名ではなく「中身」から探すための道具です。


- アプリは「グループ化」「最新候補の提示」「保管移動の案」まで。
確定と移動は、人が承認したときだけ行われます。
- ファイルを削除する機能はありません。ファイルの中身を書き換える
こともありません（読み取り専用の解析だけを行います）。
- 似ているという理由だけで別物を「同じ文書」と確定させることは
しません。候補には必ず類似度（％）と根拠を表示します。


1. フォルダを画面にドラッグ＆ドロップするか、「フォルダを開く」
から選んでください（サブフォルダを含めるか切り替えられます）。
2. 左のレールに「事件ファイル」風のグループ一覧が出ます。
- 中身が完全一致 … 中身がバイト単位で同じファイル同士
- 版の候補 … 名前の幹と中身の類似から「同じ文書の版らしい」
と判断した候補。類似度と根拠を必ず表示します
3. グループを選ぶと、中央に「版の系譜図」が出ます。古い版から
新しい版へ横一列に並び、最新の候補は大きな二重リングで
示されます。別々に直された疑いがある版は、琥珀色の分岐線で
描かれ、「どちらが最新か決められません」と正直に表示します。
4. 系譜図の節（丸）をクリックすると版の詳細が出ます。
「これを最新に指定」で人が最新を選び直せます。
「グループから外す」で候補から外せます。レールで別のグループを
選び「選んだグループと合体」で2グループを1つにできます。
5. 下半分は差分の「見開き」です。比べたい2版を選んで「差分を表示」。
文章は行単位、Excel/CSVはセル単位（シート・番地・変更前→変更後）
で色分け表示されます。
6. 「古い版の保管案」から、最新以外の版を保管フォルダへ移す案を
確認できます。移動するのはチェックして承認した分だけです。
同名のファイルがある場合は連番を付けて上書きを避けます。
「移動を元に戻す」で直前の移動を取り消せます（再起動後も可）。


1. 内容が変わった日時：Word/Excel/PowerPoint は文書内部の
メタデータ（docProps/core.xml の modified）、PDF は ModDate を
優先します。取れない場合だけファイルの更新日時を使い、
どちらの日時を使ったかを画面に明示します。
※ ファイルの更新日時はコピーやダウンロードで変わってしまう
ため、内部の日時を優先する仕組みです。
2. 差分の向き：他の版にない内容を持つ版を新しい側とみます。
3. 変更の大きさ。
2つの版が互いに相手にない内容を持つ場合は「分岐の可能性」と
警告し、単独の最新を断定しません。


- 中身を読める形式：.docx（段落）、.xlsx（セル値）、.pptx（テキスト）、
.pdf（テキスト）、.txt /.md、.csv（セル）
- それ以外の形式は、ハッシュと基本情報だけで扱います
（完全一致の判定のみ可能です）。
- 100MB を超えるファイルは中身を読まず、ハッシュのみで扱います。
- 読み取れないファイルや暗号化されたファイルは、理由と一緒に
画面の一覧に残ります（黙って捨てることはしません）。
- 2,000ファイルを超えるフォルダでは先に警告を出します。


- PDF はテキストが取り出せる場合のみ中身を比べられます。
画像だけのスキャン PDF は比較できません。
-.doc /.xls など旧形式（バイナリ形式）は中身を読めません。
- 系譜図の並び順は「内容が変わった日時」の順です。両方の版に
内部日時がない場合、順序はファイル更新日時に依存します。
- 類似度は候補提示のためだけの目安です。最終判断は人が行って
ください。
- このアプリは Windows / Mac 両対応ですが、開発環境での検証のみで、
実機の Windows / Mac での動作確認はまだ行われていません。


- Windows（EXE版）：VersionDetective-Windows.zip を展開し、
フォルダ内の VersionDetective.exe をダブルクリック。
- Windows（ソース版）：Python 3 と PySide6 が必要です。
Start-VersionDetective.bat をダブルクリック（初回だけ必要な
ライブラリを自動で入れます）。
- Mac（ソース版）：Start-VersionDetective.command をダブルクリック。
アプリ化したい場合は MakeApp-Mac.command を実行すると
dist/VersionDetective.app が作られます（universal2 を試し、
だめならこの Mac のチップ専用で自動ビルドします）。
未署名のため、初回は右クリック→「開く」が必要な場合があります。
対応は macOS 11 以降です。

【Mac版パッケージについて（正直な注記）】
配布物の VersionDetective-Mac.zip は、完成した Mac バイナリでは
ありません。Mac の実行形式は .exe ではなく .app で、開発環境
（Linux）では Mac 用バイナリを直接作ることができないため、
Mac.zip の中身はソース一式＋生成スクリプトです。お使いの Mac で
MakeApp-Mac.command を一度実行すると、その Mac 上で
VersionDetective.app が生成されます。Mac 実機での動作は未検証です。

【同梱フォントについて】
画面の文字は、アプリに同梱したフォント（欧文・数字は Inter、
日本語は Noto Sans JP）で表示します。どちらも SIL Open Font
License 1.1 のオープンソースフォントで、ライセンス全文と帰属は
fonts フォルダ内の FONTS.txt / OFL-Inter.txt /
OFL-NotoSansJP.txt に同梱しています。


設定と言語の選択、移動ログは次の場所に保存されます。
- Windows： %APPDATA%\VersionDetective
- Mac： ~/Library/Application Support/VersionDetective
通信は一切行いません（完全オフライン動作）。

------------------------------------------------
English summary
------------------------------------------------
VersionDetective finds the real latest version among
look-alike files ("final", "final 2", "final_revised", "real final")
by reading their CONTENT, not their names.

- The app only groups files, proposes the latest candidate with
visible reasons, and drafts an archive plan. A human approves
every move. Nothing is ever deleted; file contents are never
modified (read-only analysis).
- Groups: (1) identical content, (2) version candidates shown with
a similarity % and the evidence. You can remove members or merge
groups by hand.
- The main view is a version genealogy: versions on a timeline,
the latest candidate enlarged with a double ring, and a forked
amber line when two versions appear to have diverged (in that
case the app refuses to name a single "latest").
- Latest ranking prefers the content-modified datetime stored
INSIDE the document (Office docProps / PDF ModDate) over the
file mtime, because copying a file changes its mtime. The
datetime source is always shown.
- Diffs: line level for documents/text, cell level (sheet,
address, before -> after) for xlsx/csv, shown as a two-page
"spread".
- Archive moves are checkbox-approved, never overwrite (serial
suffix on clashes), are logged, and can be undone even after a
restart.
- Readable formats: docx, xlsx, pptx, pdf (text layer only), txt,
md, csv. Other formats are handled by hash only. Files over
100 MB are hashed only. Unreadable/encrypted files are listed
with the reason.
- 13 UI languages, switchable instantly from the right end of the
command bar; Arabic switches the whole layout, including the
genealogy direction, to RTL.
- Fully offline. Real Windows / Mac machines: not yet verified.
- Mac package note: VersionDetective-Mac.zip is NOT a finished Mac
binary. macOS apps are .app bundles, which cannot be compiled in
the Linux development environment used to build this app. The
zip contains the full source plus MakeApp-Mac.command; running
that script once on your own Mac builds VersionDetective.app
there (universal2 first, native fallback). Unverified on a real
Mac.
- Bundled fonts: Inter (Latin/digits) and Noto Sans JP (Japanese),
both SIL Open Font License 1.1; license texts and attribution are
in the fonts folder (FONTS.txt).

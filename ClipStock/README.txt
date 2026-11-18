ClipStock - コピペ履歴・スマートウォッチャー (Version 1.0.0)
============================================================


コピーしたテキストを自動で種類分け（URL／金額／日付／住所／コード／
メール／その他）して履歴に貯める常駐アプリです。分類は決まった形式の
判定だけで行い、各項目に「なぜその種類になったか」の根拠も表示します。

■ 使い方
- Windows（EXE版）: ClipStock.exe をダブルクリック。タスクトレイに
常駐します。パネルはトレイのアイコンか、Ctrl+Shift+V で開きます。
- Windows（ソース版）: Start-ClipStock.bat をダブルクリック。
自分でEXEを作る場合は MakeExe-ClipStock.bat を使います。
- Mac: Start-ClipStock.command で起動（ソース版）。
.app化は MakeApp-Mac.command をダブルクリック（キット形式）。
- パネルで項目をクリックすると、そのテキストがクリップボードに戻り
ます。貼り付け自体は、貼りたい場所で Ctrl+V（Macは Command+V）を
押して人が行います。アプリが勝手に貼ることはありません。

■ 作業セット
コピーの間隔が設定時間（初期設定30分）以上あくと、自動で新しい
「作業セット」に分かれます。「新しいセットを開始」ボタンで手動で
区切ることもでき、名前も変えられます。

■ プライバシー（大切な注意）
- 履歴はこのパソコンの中だけに保存されます。通信は一切しません。
- パスワードなど人に見せたくないものも、コピーすれば履歴に残ります。
残したくない時は「記録を一時停止」してください。
- カード番号らしい形式（チェックディジット一致）は、初期設定では
保存しません（設定で変更できます）。
- 履歴は初期設定で24時間たつと自動で消えます（変更可）。ピン留め
した項目は自動消去されません。

■ Macでの制限（正直なお知らせ）
- Mac版ではグローバルホットキー（Ctrl+Shift+V）は使えません。
パネルはメニューバーのアイコンから開いてください。
- Mac版は未署名のため、初回は右クリック→「開く」が必要です。
- Macでの自動起動はアプリ内設定では行えません。システム設定の
「ログイン項目」に手動で追加してください。

■ 保存場所
- Windows: %APPDATA%\ClipStock （settings.json / history.json）
- Mac: ~/Library/Application Support/ClipStock

■ 動作環境
- Windows 10/11（64bit）、macOS 11以降
- 画面表示は13言語に切替できます（設定画面の「表示言語」）。

------------------------------------------------------------

ClipStock (Version 1.0.0) - clipboard history watcher.
Copied text is sorted automatically into kinds (URL / amount / date /
address / code / email / other) using fixed format rules only, and each
item shows the reason for its kind. History is stored ONLY on your
computer - the app never communicates over the network.

- Windows (EXE): run ClipStock.exe. It lives in the task tray; open
the panel from the tray icon or with Ctrl+Shift+V.
- Windows (source): Start-ClipStock.bat. To build your own EXE, use
MakeExe-ClipStock.bat.
- Mac: Start-ClipStock.command (source), or build an.app with
MakeApp-Mac.command (kit form).
- Click an item in the panel to put it back on the clipboard. Pasting
itself is always done by you (Ctrl+V / Command+V). The app never
pastes on its own.
- Work sets: copies split into a new set after a quiet gap (30 min by
default), or manually with the "Start a new set" button.
- Privacy: passwords and other private text WILL stay in the history
if you copy them - use "Pause recording" when needed. Card-number
shaped text (checksum match) is not saved by default. History is
auto-deleted after 24 hours by default (configurable); pinned items
are kept.
- Mac limitations: the global hotkey is Windows-only (open the panel
from the menu-bar icon); the app is unsigned, so right-click > Open
on first launch; autostart on Mac is via System Settings > Login
Items, not from inside the app.
- Data: Windows %APPDATA%\ClipStock, Mac ~/Library/Application
Support/ClipStock. UI available in 13 languages.

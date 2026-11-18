スクショ安心フィルター / RedactShot
================================================

これは何をするアプリ？ / What is this app?
------------------------------------------------

スクリーンショットを共有・送信する前に、写り込んだ個人情報や
社外秘情報を隠すための Windows / Mac デスクトップアプリです。

・画像（PNG / JPG / BMP / WebP）を開く、貼り付ける、または
ドラッグ＆ドロップすると、OCRで文字を読み取り、メールアドレス・
電話番号・カード番号・金額・パスワード欄付近・伏せ字・登録した
社外秘用語などを「候補」として自動検出します
・候補は右側の一覧でカテゴリ・検出テキスト・根拠とともに表示され、
チェックのオン／オフでプレビューに即時反映されます。カテゴリ
単位の一括オン／オフもできます。パスワードは「候補（推定）」と
明示されます（確定ではありません）
・効果はモザイク／ぼかし／黒塗りの3種類から選べます。効果の強さは、
弱いと文字が読めてしまうため、すべての効果で安全なレベルに
固定されており変更できません
・画像の上でドラッグして手動で範囲を追加でき、移動・リサイズ・
Deleteキーでの削除もできます
・書き出しは必ず「最終プレビュー」で完成画像を確認してから行います。
保存時の初期名は「元の名前_redacted」です。元のファイルと
同じ場所（同一パス）への保存は、警告して阻止します
・クリップボードへのコピーもできます


A Windows / Mac desktop app that hides personal and confidential
information in screenshots before you share or send them.
Open, paste, or drag & drop an image (PNG / JPG / BMP / WebP); OCR
detects candidates such as email addresses, phone numbers, card
numbers, money amounts, text near password fields, masked characters,
and your registered confidential terms. Candidates appear in a list
with category, detected text, and reason, and toggling them updates
the live preview (pixelate / blur / blackout; effect strength is
fixed at a safe, unreadable level for every effect, because a weak
effect can leave text readable, and cannot be weakened).
You can also add regions manually by dragging, move / resize them,
and delete them with the Delete key. Export always goes through a
final-preview confirmation dialog; the default file name is
"<original>_redacted", and saving over the original path is blocked
with a warning. Copying to the clipboard is also supported.

完全オフライン / Fully offline
------------------------------------------------
このアプリはネットワーク通信を行いません。画像も検出
結果も外部に送信されません。
This app makes no network connections. Images and
detection results are never sent anywhere.

元画像は変更しません / The original is never modified
------------------------------------------------
元画像ファイルは一切変更しません。効果はコピーに対して
適用され、別名で保存します。同一パスへの上書き保存は阻止します。
The original image file is never modified. Effects are
applied to a copy and saved under a different name; saving to the
exact same path is blocked.

Windows での起動 / Running on Windows
------------------------------------------------

・EXE版: RedactShot.exe をダブルクリックします（Python不要）。
・ソース版: ZIPを「すべて展開」し、展開したフォルダーで
Start-RedactShot.bat をダブルクリックします。初回だけ必要な
ライブラリ（PySide6 / Pillow）を自動で入れます。黒い画面は
使用中は開いたままにしてください。
・ソース版でOCRを使う場合は Tesseract OCR が別途必要です。
見つからない場合は案内が表示され、手動範囲のみで使えます。

- EXE build: double-click RedactShot.exe (no Python needed).
- Source build: extract the ZIP fully, then double-click
Start-RedactShot.bat in the extracted folder. Required libraries
(PySide6 / Pillow) are installed automatically on first run.
Keep the black console window open while using the app.
- OCR in the source build needs Tesseract OCR installed separately.
If it is not found, a notice is shown and manual regions still work.

Mac での起動 / Running on Mac
------------------------------------------------

対応環境は macOS 11（Big Sur）以降を想定しています。Mac版は、
ダウンロード後に Mac 自身で.app を組み立てる方式です。
1. ZIPを展開します
2. MakeApp-Mac.command をダブルクリックします（開けない場合は
右クリックして「開く」を選びます）
3. Python 3.10以降が無い場合は、案内に従って python.org または
Homebrew で Python を入れてから再実行します
4. MakeApp はまず universal2（Intel + Apple Silicon 両対応）を
試し、失敗した場合はその Mac のチップ専用形式で作り直し、
最後にどちらで作ったかを表示します
5. dist フォルダーに RedactShot.app ができます
・すぐに試したい場合は Start-RedactShot.command でソース版を
直接起動できます
・Mac用OCRには Tesseract が別途必要で、同梱しません。Homebrewで
次を実行してください: brew install tesseract
見つからない場合、OCRだけが使えず、手動範囲は使えます
・署名のないアプリのため、初回は Finder で右クリック→「開く」で
確認してください

Target: macOS 11 (Big Sur) or later. The Mac build is assembled on
your own Mac after download:
1. Extract the ZIP. 2. Double-click MakeApp-Mac.command
(if blocked, right-click and choose Open).
3. If Python 3.10+ is missing, install it from python.org or
Homebrew, then run MakeApp-Mac.command again.
4. MakeApp tries universal2 first, falls back to your Mac's native
architecture, and reports which one was built at the end.
5. RedactShot.app appears in the dist folder.
To try quickly, Start-RedactShot.command runs the source directly.
OCR on Mac needs Tesseract separately (not bundled):
brew install tesseract
Without it, only OCR is unavailable; manual regions still work.
The app is unsigned, so confirm the first launch via right-click > Open.

設定の保存先 / Settings location
------------------------------------------------
設定（言語・社外秘用語・既定の効果・カテゴリ初期値）は
settings.json に保存されます。
Windows: %APPDATA%\RedactShot\settings.json
Mac: ~/Library/Application Support/RedactShot/settings.json
Linux: ~/.local/share/RedactShot/settings.json

同梱ファイル（ソース版） / Files (source build)
------------------------------------------------
app.py / appinfo.py / i18n.py … アプリ本体・表示名・多言語文字列
detect.py / effects.py / ocr.py … 検出・効果・OCRエンジン
requirements.txt … 必要なライブラリ（PySide6, Pillow）
Start-RedactShot.bat … Windows ソース版起動用
Start-RedactShot.command … Mac ソース版起動用
MakeApp-Mac.command … Mac で.app を生成する用
README.txt … このファイル

正直な制限 / Honest limitations
------------------------------------------------

・本アプリは Linux 上のオフスクリーン／エミュレーション環境での
起動確認までで、実物の Windows パソコンおよび実機 Mac での
起動はまだ未検証です。
・OCRの精度は画像の状態に依存します。検出候補と最終プレビューを
必ず目で確認してください。特にパスワード候補は推定です。
・候補の検出は決定的なパターン照合に基づきます。検出漏れがあり
得るため、書き出し前の最終確認が重要です。

- Verified only in Linux offscreen / emulation environments so far;
launching on a real Windows PC and on a real Mac is NOT yet verified.
- OCR accuracy depends on image quality. Always check the candidates
and the final preview yourself; password candidates are estimates.
- Detection is pattern-based and can miss items, so the final
preview check before export matters.

対応言語 / Languages
------------------------------------------------
画面表示は13言語に切り替えできます（日本語・English・Español・
简体中文・Français・Deutsch・Português・Русский・Italiano・Türkçe・
العربية・Bahasa Indonesia・한국어）。アラビア語は右から左（RTL）
表示になります。選んだ言語は保存されます。
The UI switches instantly among 13 languages; Arabic uses RTL layout.
Your language choice is saved.

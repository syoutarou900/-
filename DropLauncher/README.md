# 超特化型ドロップランチャー（DropLauncher）

デスクトップに常駐する小さなフローティングパネルに、ファイルをドラッグ＆ドロップするだけで
定型作業を自動処理する、世界中の一般のWindows PCユーザー向けの汎用アプリです。
特定の機種・ユーザー名・フォルダ構成には依存しません。

## 動作環境
- Windows 10 / 11（64bit）、メーカー不問。内蔵GPUのみのPCでも軽く動きます。
- **EXE版は Python 不要**で、単体で起動できます（これが本線です）。
- 管理者権限は不要です。設定・ログ・出力はすべてユーザーフォルダ側に保存されます。
  - 既定の出力先：ドキュメントフォルダ内の `DropLauncher-Out`（Windowsの既知フォルダから取得。言語・ユーザー名に依存しません）
  - 設定ファイル：アプリと同じフォルダに書けない場合は `%LOCALAPPDATA%\DropLauncher` に保存されます。
- 署名について（正直なお知らせ）：このEXEにはデジタル署名がありません。そのため初回起動時に
  Windows SmartScreen の警告（「WindowsによってPCが保護されました」）が出る場合があります。
  その場合は「詳細情報」→「実行」を押すと起動できます。

## 使い方（EXE版・本線）
1. ZIPをダウンロードします。
2. ZIPを右クリック→「すべて展開」で展開します（展開せずに中身を直接実行しないでください）。
3. 展開したフォルダ内の `DropLauncher.exe` をダブルクリックします。
4. パネルが表示されたら、処理したいファイルを各ゾーンへドラッグ＆ドロップします。

## 使い方（ソース版・予備）
Python 3.10〜3.13 がある場合のみ使える予備の方法です。
展開したフォルダで `Start-DropLauncher.bat` をダブルクリックしてください。
初回だけライブラリ（約180MB）を自動ダウンロードします。2回目以降は確認だけで数秒で起動します。
黒い窓（コマンドプロンプト）はアプリ使用中は開いたままにしてください。閉じるとアプリも終了します。
※ .bat ファイルは日本語Windows向けに Shift-JIS で書かれています。他言語のWindowsでは
　文字化けする場合があるため、EXE版の利用を推奨します。

## 自分でEXEを作る場合
`MakeExe-DropLauncher.bat` を実行すると `dist\DropLauncher.exe` が作成されます
（Python とネット接続が必要です。動画変換用 ffmpeg もEXE内に同梱されます）。

## Macで使う場合（ソース版ZIPに同梱）
プログラム自体はWindows版と共通で、Macでも同じ機能・同じ13言語UIが使えます。
ただし **Mac実機での動作確認はまだ行えていません**（開発環境にMacがないため）。
対応OSは **macOS 11（Big Sur）以降** です。

### 手順A：そのまま起動する（Pythonが必要）
1. ソース版ZIPをダウンロードして展開します。
2. 展開したフォルダ内の `Start-DropLauncher.command` をダブルクリックします。
   初回だけ、未署名のため macOS に止められる場合があります。その場合はファイルを
   **右クリック→「開く」** を選ぶと起動できます（Gatekeeperの仕様です）。
3. 初回は仮想環境の作成とライブラリの自動インストール（要ネット接続）が走ります。
   Python 3 が無いMacでは、入手方法（python.org / Homebrew / Command Line Tools）が
   画面に表示されて終了しますので、先にPython 3を入れてから再度実行してください。

### 手順B：.app化する（普段はこちらが便利）
1. 展開したフォルダ内の `MakeApp-Mac.command` をダブルクリックします
   （初回は上と同じく右クリック→「開く」が必要な場合があります）。
2. ビルドが終わると `dist/DropLauncher.app` ができます。以後はその .app を
   ダブルクリックして使えます（.app の初回起動時も右クリック→「開く」が要る場合があります）。
3. チップの扱い：まず両チップ対応の **universal2** での生成を試み、作れなかった場合は
   **そのMacのチップ専用**（Apple Silicon機ではarm64、Intel機ではx86_64）に自動で
   切り替わります。どちらで作れたかはビルド終了時に画面に表示されます。
   チップ専用で作った .app は、別のチップのMacでは動かないため、そのMacで作り直してください。

### Macでの保存先・仕様の違い（正直なお知らせ）
- 設定・ログの保存先：`~/Library/Application Support/DropLauncher`
  （出力先の既定はWindowsと同じく `~/Documents/DropLauncher-Out` です）
- 動画変換の ffmpeg：ソース版ではライブラリ（imageio-ffmpeg）に含まれるMac用バイナリを
  自動で使います。同梱ツール・Homebrew（`/opt/homebrew/bin/ffmpeg` 等）の順でも探します。
  見つからない場合は起動時のログに「見つかりません」と表示されます
  （その場合は `brew install ffmpeg` で入れるか、設定は不要で imageio-ffmpeg 入りの
  ソース版をそのまま使ってください）。
- Excel→PDF：Macでは LibreOffice（`/Applications/LibreOffice.app` または Homebrew版）が
  あればそれを使います。**Microsoft Office連携（COM）はWindows専用のためMacでは使えません。**
  LibreOfficeが無い場合は、従来どおり「書式つきHTML（PDFではありません）」を代替出力し、
  使われたエンジンはログに明記されます。
- フォルダーを開くボタンは、Macでは Finder で開きます。
- 本アプリに自動起動（ログイン時起動）の機能は元々ありません（Windows版・Mac版とも）。

## 機能（10ゾーン）
1. 転記ヘルパー：PDF/Excel/CSV/TXT/EML → 書式つきExcel・CSV・TXT。Excel入力は書式コピー版も出力。
2. 仕分け＆リネーム：日付_案件名_連番（例 20261112_作業_001.pdf）に改名し、拡張子/日付フォルダへ移動（設定でコピー可）。「仕分けを元に戻す」ボタンで直前のバッチを取り消せます。
3. 日報集計：Excel/CSV の件数・数値列合計・「完了」件数を集計し、報告文（.txt＋クリップボード）と集計サマリー.xlsx を作成。
4. 画像 一括変換：最大幅1200px（設定可）にリサイズ、目標500KB以下（設定可）を目指して画質を自動調整、JPG/WebP/PNG へ変換。EXIFの向きも補正します。※500KBは目標値で、画像によっては画質下限の都合で上回る場合があります。
5. PDF結合：複数PDFを1つに結合（日付_案件名_結合.pdf）。
6. PDF分割・抽出：ページごとのPDFに分割＋テキスト抽出。
7. 動画変換（ffmpeg内蔵）：MP4変換（H.264/AAC）／圧縮720p（CRF28）／音声抽出MP3／GIF変換。パネル上部のプリセットで切替。処理は裏側で動き、画面は固まりません。
8. Excel変換：xlsx→PDF（エンジン優先順位：LibreOffice → Microsoft Office（COM）→ 書式つきHTML代替）、xlsx→CSV、xlsx→HTML。docx/pptx のPDF変換も LibreOffice / Office があれば対応。
   ※純PythonのHTML代替は「書式を再現したHTML」であり、Excelと100%同一の見た目を保証するものではありません。使われたエンジンはログに明記されます。
9. ZIP圧縮：複数ファイル／フォルダを 日付_案件名.zip にまとめます。
10. ZIP解凍：ZIPを新しいフォルダへ展開（日本語ファイル名・危険なパスの対策つき）。

## 設定
パネルの「設定」ボタンから、出力先フォルダ・案件名・仕分け方法（移動/コピー）・サブフォルダ方式・
画像の最大幅/目標KB/形式・LibreOffice（soffice）の場所を変更できます。

## ログ・履歴
- 処理履歴（仕分けの取り消し用）：出力先フォルダの `history.json`
- エラーログ：`DropLauncher-error.log`（設定保存先フォルダ内）

## ファイル構成
- DropLauncher.exe（EXE版のみ） / app.py / core.py / requirements.txt
- Start-DropLauncher.bat（予備起動） / MakeExe-DropLauncher.bat（EXE作成）

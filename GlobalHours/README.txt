タイムゾーン・営業時間チェッカー（GlobalHours）

海外の取引先の現地時間・営業時間・週末・祝日を一目で確認し、
双方の営業時間に収まる会議候補と、相手の言語の提案文を用意する
デスクトップアプリです。送信機能はありません（決めるのは人です）。

■ Windows（EXE版）
  GlobalHours-Windows.zip を展開し、GlobalHours.exe を実行してください。
  Python は不要です。

■ Windows（ソース版）／ Mac（ソースキット）
  Python 3.10 以上が必要です。
  Windows: Start-GlobalHours.bat をダブルクリック
  Mac:     Start-GlobalHours.command をダブルクリック
           （.app を作る場合は MakeApp-Mac.command）

■ データの保存先
  設定と取引先リストは次の場所に保存されます。
  Windows: %APPDATA%\GlobalHours\settings.json
  Mac:     ~/Library/Application Support/GlobalHours/settings.json

■ 画面テーマ（ダーク／ライト）
  画面右上のボタン1つで、ダーク（夜空）とライト（明るい画面）を
  再起動なしで瞬時に切り替えられます。選んだテーマは保存され、
  次回起動時もそのまま使えます。

■ 完全オフライン
  時差計算（IANAタイムゾーンデータ）と祝日データは同梱されており、
  ネット接続なしで使えます。

Timezone & business-hours checker for overseas partners.
Shows each partner's local time, business hours, weekends and
public holidays on one "world time band" map, proposes meeting
slots that fit both sides, and drafts a proposal message in the
partner's language. It never sends anything. Fully offline.

ContextStruct - Source Code (version 1.0.0)
============================================================
This ZIP contains the full source code of ContextStruct, published so that
anyone can inspect what the app does, or build it themselves.
マルウェアやスパイウェアの類は含まれていません。中身を自由にご確認ください。


- Python 3.11 or later
- pip install -r requirements.txt


- Windows: Start-ContextStruct.bat (or: python app.py)
- Mac: Start-ContextStruct.command (or: python3 app.py)


- Windows (.exe): MakeExe-*.bat (uses PyInstaller) — if included
- Mac (.app): MakeApp-Mac.command

Notes:
AIモデル（約2.8GB）と推論ランタイムのバイナリは含まれていません。モデルはアプリの初回起動時に自動でダウンロードされます。OCR機能にはTesseract（別途インストール）が必要です。
The AI model (about 2.8 GB) and the inference runtime binaries are not included. The model is downloaded automatically on first launch. The OCR features require Tesseract (installed separately).



(c) 2026 Furutaka (フルタカ)
The app is free for personal and commercial use.
このアプリは個人利用・商用利用ともに完全無料です。
Source published for transparency. / 透明性のために公開しています。
Site: https://theta-three-28.vercel.app/

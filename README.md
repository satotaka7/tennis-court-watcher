# tennis-court-watcher
テニスコートの空き状況を確認して LINE へ通知するツール（公開用ひな形）。

## 使い方
1. 依存関係をインストール
   - `pip install -r requirements.txt`
2. Playwright のブラウザをインストール（初回のみ）
   - `python -m playwright install chromium`
3. `.env` を作成（トークン等は GitHub に上げない）
   - `LINE_CHANNEL_ACCESS_TOKEN` を設定
   - `TENNIS_AVAILABLE_OVERRIDE` は動作確認用の強制通知スイッチです（任意）
4. 通知テスト
   - `python send_line_test.py`
5. メイン処理
   - `python main.py`

## 環境変数
- `LINE_CHANNEL_ACCESS_TOKEN`: LINE Messaging API の Channel access token
- `LINE_MESSAGE`: 通知文（未設定の場合はデフォルト文言）
- `TENNIS_AVAILABLE_OVERRIDE`: `1` / `true` / `yes` のときスクレイピングをスキップして固定文言で通知（任意）
- `SEARCH_ANCHOR_DATE`: 空き状況検索の「利用日」に使う日付 `YYYY-MM-DD`（未設定なら当日。サイトは **その利用日から7日間** が列になる）
- `BROWSER_SLOW_MO_MS`: Playwright の slow_mo（デバッグ用、デフォルト `0`）

## 注意
本ツールはサイトへアクセスして空き状況を確認します。過剰な回数のアクセスは避けてください。

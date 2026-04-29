# tennis-court-watcher
テニスコートの空き状況を確認して LINE へ通知するツール（公開用ひな形）。

## 使い方
1. 依存関係をインストール
   - `pip install -r requirements.txt`
2. `.env` を作成（トークン等は GitHub に上げない）
   - `LINE_CHANNEL_ACCESS_TOKEN` を設定
   - `TENNIS_AVAILABLE_OVERRIDE` は現在は仮ゲート（未実装のため）です
3. 通知テスト
   - `python send_line_test.py`
4. メイン処理
   - `python main.py`

## 環境変数
- `LINE_CHANNEL_ACCESS_TOKEN`: LINE Messaging API の Channel access token
- `LINE_MESSAGE`: 通知文（未設定の場合はデフォルト文言）
- `TENNIS_AVAILABLE_OVERRIDE`: `1` / `true` / `yes` のとき通知、その他は通知しない（現時点の判定仮）

## 注意
現状 `main.py` の空き判定はスクレイピング未実装のため、`TENNIS_AVAILABLE_OVERRIDE` の値で通知が制御されます。

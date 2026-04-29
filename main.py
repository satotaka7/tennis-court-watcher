import os
import sys

from dotenv import load_dotenv
from linebot.v3.messaging import (
    ApiClient,
    BroadcastRequest,
    Configuration,
    MessagingApi,
    TextMessage,
)

DEFAULT_MESSAGE = "テニスコートの空きが出たよ！"


def _str_to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def broadcast_text(*, channel_access_token: str, text: str) -> None:
    """
    LINE Messaging API にブロードキャスト送信する。

    `channel_access_token` は `.env` から読み込む（GitHub へは上げない）。
    """

    configuration = Configuration(access_token=channel_access_token)
    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        messaging_api.broadcast(
            BroadcastRequest(messages=[TextMessage(text=text)])
        )


def check_tennis_court_availability() -> bool:
    """
    テニスコート空き状況の判定。

    現時点ではスクレイピング実装がないため、環境変数で制御する仮ゲートを用意しています。
    """

    override = os.getenv("TENNIS_AVAILABLE_OVERRIDE")
    if override is None:
        return False
    return _str_to_bool(override)


def main() -> int:
    load_dotenv()

    channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    if not channel_access_token:
        print(
            "LINE_CHANNEL_ACCESS_TOKEN が見つかりません。.env を作成して設定してください。",
            file=sys.stderr,
        )
        return 2

    message = os.getenv("LINE_MESSAGE", DEFAULT_MESSAGE)

    if check_tennis_court_availability():
        broadcast_text(channel_access_token=channel_access_token, text=message)
        print("通知を送信しました。")
        return 0

    print("空きなし（または判定未実装）。通知しません。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


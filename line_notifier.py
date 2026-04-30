"""LINE通知"""

import sys
from linebot.v3.messaging import (
    ApiClient,
    BroadcastRequest,
    Configuration,
    MessagingApi,
    TextMessage,
)


def broadcast_text(*, channel_access_token: str, text: str) -> None:
    """LINE Messaging API にブロードキャスト送信する"""
    configuration = Configuration(access_token=channel_access_token)
    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        messaging_api.broadcast(
            BroadcastRequest(messages=[TextMessage(text=text)])
        )


def format_slot_message(slots: list) -> str:
    """空きスロットのメッセージを作成"""
    lines: list[str] = []
    for s in slots:
        lines.append(f"{s.day.isoformat()} {s.label}")
    return "\n".join(lines)


def send_notification(
    *,
    channel_access_token: str,
    message: str,
    slot_count: int = 0,
    debug: bool = False,
) -> None:
    """LINEに通知を送信（デバッグモード対応）"""
    if debug:
        print(f"[DEBUG] 送信メッセージ: {message}", file=sys.stderr)
    broadcast_text(channel_access_token=channel_access_token, text=message)
    print(f"通知を送信しました。検出: {slot_count} 件")
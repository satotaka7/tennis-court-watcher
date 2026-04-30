"""エントリーポイント"""

import sys

from config import (
    load_env,
    get_line_channel_token,
    get_line_message,
    get_browser_slow_mo,
    get_tennis_available_override,
    SPORT_LABEL,
    PARK_LABEL,
)
from date_utils import str_to_bool, parse_anchor_date_from_env, seven_days_from_anchor
from line_notifier import broadcast_text, format_slot_message
from scraper import fetch_availability_slots


def check_tennis_court_availability() -> bool:
    """テニスコート空き状況の判定（テスト用オーバーライド）"""
    override = get_tennis_available_override()
    if override is None:
        return False
    return str_to_bool(override)


def main() -> int:
    # 環境変数を読み込む
    load_env()

    channel_access_token = get_line_channel_token()
    if not channel_access_token:
        print(
            "LINE_CHANNEL_ACCESS_TOKEN が見つかりません。.env を作成して設定してください。",
            file=sys.stderr,
        )
        return 2

    # override が有効なら、従来通り固定文言で通知（動作確認用）
    if check_tennis_court_availability():
        message = get_line_message()
        broadcast_text(channel_access_token=channel_access_token, text=message)
        print("通知を送信しました（override）。")
        return 0

    use_day = parse_anchor_date_from_env()
    slow_mo_ms = get_browser_slow_mo()

    slots = fetch_availability_slots(use_day=use_day, slow_down_ms=slow_mo_ms)
    if slots:
        wk = seven_days_from_anchor(use_day)
        day0, day6 = wk[0], wk[-1]
        header = (
            f"【空きあり】{PARK_LABEL} / {SPORT_LABEL} "
            f"（表示週 {day0.isoformat()}〜{day6.isoformat()}・土日祝のみ通知）"
        )
        body = format_slot_message(sorted(slots, key=lambda s: (s.day, s.label)))
        message = f"{header}\n{body}"
        broadcast_text(channel_access_token=channel_access_token, text=message)
        print(f"通知を送信しました。検出: {len(slots)} 件")
        return 0

    print("空きなし。通知しません。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

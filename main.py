"""エントリーポイント"""

import sys

from config import (
    load_env,
    get_line_channel_token,
    get_line_message,
    get_browser_slow_mo,
    get_tennis_available_override,
    load_targets,
    is_sumida_enabled,
)
from date_utils import str_to_bool, parse_anchor_date_from_env, seven_days_from_anchor
from line_notifier import broadcast_text, format_slot_message
from scraper import fetch_availability_slots
from scraper_sumida import fetch_availability_slots_sumida


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
    targets = load_targets()

    wk = seven_days_from_anchor(use_day)
    day0, day6 = wk[0], wk[-1]

    def sort_key(s):
        return (s.day, int(s.label.rstrip('時')) if s.label.rstrip('時').isdigit() else 99)

    sections = []
    total = 0
    for park_label, sport_label in targets:
        slots = fetch_availability_slots(
            use_day=use_day,
            slow_down_ms=slow_mo_ms,
            park_label=park_label,
            sport_label=sport_label,
        )
        if slots:
            body = format_slot_message(sorted(slots, key=sort_key))
            sections.append(f"■ {park_label} / {sport_label}\n{body}")
            total += len(slots)

    if is_sumida_enabled():
        sumida_slots = fetch_availability_slots_sumida(slow_down_ms=slow_mo_ms)
        if sumida_slots:
            body = format_slot_message(sorted(sumida_slots, key=lambda s: (s.day, s.label)))
            sections.append(f"■ 墨田区 / 硬式テニス\n{body}")
            total += len(sumida_slots)

    if sections:
        header = f"【空きあり】（表示週 {day0.isoformat()}〜{day6.isoformat()}・土日祝のみ通知）"
        message = header + "\n\n" + "\n\n".join(sections)
        broadcast_text(channel_access_token=channel_access_token, text=message)
        print(f"通知を送信しました。検出: {total} 件")
        return 0

    print("空きなし。通知しません。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

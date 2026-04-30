"""日付ユーティリティ"""

import os
from datetime import date, timedelta

import jpholiday


def str_to_bool(value: str) -> bool:
    """文字列を真偽値に変換"""
    return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def is_weekend_or_holiday(d: date) -> bool:
    """土日祝か判定"""
    return d.weekday() >= 5 or jpholiday.is_holiday(d)


def seven_days_from_anchor(anchor: date) -> list[date]:
    """サイトの表示に合わせ、利用日（アンカー）から続く連続7日分（列順と対応）

    例: 利用日が 4/30(木) なら [4/30 … +6日] の 7日分が列と対応する。
    """
    return [anchor + timedelta(days=i) for i in range(7)]


def parse_anchor_date_from_env() -> date:
    """SEARCH_ANCHOR_DATE が YYYY-MM-DD ならそれを利用日に、未設定なら今日"""
    raw = (os.getenv("SEARCH_ANCHOR_DATE") or "").strip()
    if not raw:
        return date.today()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return date.today()
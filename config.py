"""設定・定数"""

import csv
import io
import os
import sys
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

# デフォルト設定
DEFAULT_MESSAGE = "テニスコートの空きが出たよ！"
SPORT_LABEL = "テニス（人工芝）"
PARK_LABEL = "舎人公園"
START_URL = "https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"

# 環境変数キーの定義
ENV_KEY_LINE_TOKEN = "LINE_CHANNEL_ACCESS_TOKEN"
ENV_KEY_TARGETS_SHEET_ID = "TARGETS_SHEET_ID"
ENV_KEY_LINE_MESSAGE = "LINE_MESSAGE"
ENV_KEY_SEARCH_ANCHOR_DATE = "SEARCH_ANCHOR_DATE"
ENV_KEY_BROWSER_SLOW_MO_MS = "BROWSER_SLOW_MO_MS"
ENV_KEY_DEBUG_SLOTS = "DEBUG_SLOTS"
ENV_KEY_TENNIS_AVAILABLE_OVERRIDE = "TENNIS_AVAILABLE_OVERRIDE"


def load_env() -> None:
    """環境変数を .env ファイルから読み込む"""
    # 現在の作業ディレクトリまたはこのファイルの親ディレクトリから .env を検索
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        env_path = Path(__file__).parent.with_name(".env")
    load_dotenv(dotenv_path=env_path, override=False)


def get_line_channel_token() -> str | None:
    """LINE Channel Access Token を取得"""
    return os.getenv(ENV_KEY_LINE_TOKEN)


def get_line_message() -> str:
    """通知メッセージを取得"""
    return os.getenv(ENV_KEY_LINE_MESSAGE, DEFAULT_MESSAGE)


def get_browser_slow_mo() -> int:
    """Playwright の slow_mo ミリ秒を取得"""
    return int(os.getenv(ENV_KEY_BROWSER_SLOW_MO_MS, "0"))


def is_debug_slots() -> bool:
    """デバッグモードか"""
    return os.getenv(ENV_KEY_DEBUG_SLOTS, "").strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def get_tennis_available_override() -> str | None:
    """テスト用オーバーライド値を返す"""
    return os.getenv(ENV_KEY_TENNIS_AVAILABLE_OVERRIDE)


def load_targets() -> list[tuple[str, str]]:
    """スプレッドシートから (park_label, sport_label) のリストを返す。
    シートが未設定の場合は PARK_LABEL / SPORT_LABEL のペアにフォールバックする。
    """
    sheet_id = os.getenv(ENV_KEY_TARGETS_SHEET_ID, "").strip()
    if sheet_id:
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                text = resp.read().decode("utf-8")
            reader = csv.DictReader(io.StringIO(text))
            targets = [
                (row["park_label"].strip(), row["sport_label"].strip())
                for row in reader
                if row.get("park_label", "").strip() and row.get("sport_label", "").strip()
            ]
            if targets:
                return targets
        except Exception as e:
            print(f"[WARNING] スプレッドシート読み込みエラー: {e}", file=sys.stderr)
    return [(PARK_LABEL, SPORT_LABEL)]
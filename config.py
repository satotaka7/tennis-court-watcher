"""設定・定数"""

import os
from pathlib import Path
from dotenv import load_dotenv

# デフォルト設定
DEFAULT_MESSAGE = "テニスコートの空きが出たよ！"
SPORT_LABEL = "テニス（人工芝）"
PARK_LABEL = "舎人公園"
START_URL = "https://kouen.sports.metro.tokyo.lg.jp/web/index.jsp"

# 環境変数キーの定義
ENV_KEY_LINE_TOKEN = "LINE_CHANNEL_ACCESS_TOKEN"
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
"""データモデル"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class AvailableSlot:
    """空きスロット"""

    day: date
    label: str
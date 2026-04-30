from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


WEEKDAY_BY_RU: dict[str, int] = {
    "понедельник": 0,
    "понедельника": 0,
    "вторник": 1,
    "вторника": 1,
    "среду": 2,
    "среда": 2,
    "четверг": 3,
    "четверга": 3,
    "пятницу": 4,
    "пятница": 4,
    "субботу": 5,
    "суббота": 5,
    "воскресенье": 6,
}


@dataclass(frozen=True)
class ParsedTaskDraft:
    title: str
    description: str
    planned_at: datetime | None
    due_at: datetime | None
    reminder_at: datetime | None
    ambiguous: bool
    metadata: dict[str, object]


class NaturalLanguageTaskParser:
    """Small deterministic Russian task parser used before/alongside LLM parsing.

    It deliberately marks broad relative dates as ambiguous so the agent asks
    a clarifying question instead of inventing operational dates.
    """

    def parse(
        self, text: str, *, timezone: str, now: datetime | None = None
    ) -> list[ParsedTaskDraft]:
        tz = ZoneInfo(timezone)
        current = now.astimezone(tz) if now else datetime.now(tz)
        normalized = " ".join(text.strip().split())
        if not normalized:
            return []

        reminder_time = self._extract_time(normalized) or time(9, 0)
        planned_at, ambiguous = self._extract_date(normalized, current, reminder_time)
        title = self._clean_title(normalized)
        return [
            ParsedTaskDraft(
                title=title,
                description=normalized,
                planned_at=planned_at,
                due_at=planned_at,
                reminder_at=planned_at,
                ambiguous=ambiguous,
                metadata={
                    "parser": "deterministic_ru_v1",
                    "date_ambiguous": ambiguous,
                    "extracted_time": reminder_time.isoformat(timespec="minutes"),
                },
            )
        ]

    @staticmethod
    def _extract_time(text: str) -> time | None:
        match = re.search(r"(?:в|к)\s*(\d{1,2})(?::(\d{2}))?\s*(?:час(?:ов|а)?)?", text)
        if not match:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return time(hour, minute)
        return None

    def _extract_date(
        self, text: str, now: datetime, reminder_time: time
    ) -> tuple[datetime | None, bool]:
        lowered = text.lower()
        if "сегодня" in lowered:
            return self._combine(now, 0, reminder_time), False
        if "завтра" in lowered:
            return self._combine(now, 1, reminder_time), False
        for word, weekday in WEEKDAY_BY_RU.items():
            if word in lowered:
                days_ahead = (weekday - now.weekday()) % 7
                if "следующ" in lowered and days_ahead == 0:
                    days_ahead = 7
                elif days_ahead == 0 and self._combine(now, 0, reminder_time) <= now:
                    days_ahead = 7
                return self._combine(now, days_ahead, reminder_time), False
        if (
            "следующей неделе" in lowered
            or "следующую неделю" in lowered
        ):
            return None, True
        return None, True

    @staticmethod
    def _combine(now: datetime, days_ahead: int, value: time) -> datetime:
        target = now.date() + timedelta(days=days_ahead)
        return datetime.combine(target, value, tzinfo=now.tzinfo)

    @staticmethod
    def _clean_title(text: str) -> str:
        cleaned = re.sub(r"^(привет[,!\s]*)", "", text, flags=re.IGNORECASE)
        commands = [
            "напомни мне",
            "напомни",
            "создай задачу",
            "надо",
            "нужно",
        ]
        command_pattern = "|".join(commands)
        cleaned = re.sub(rf"\b({command_pattern})\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = " ".join(cleaned.split()).strip(" ,.!;:")
        return cleaned[:300] or "Задача"

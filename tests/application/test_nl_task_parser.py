from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.application.nl_task_parser import NaturalLanguageTaskParser


def test_parser_extracts_tomorrow_at_8() -> None:
    parser = NaturalLanguageTaskParser()
    now = datetime(2026, 4, 30, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))

    result = parser.parse(
        "Напомни завтра в 8 позвонить Игорю",
        timezone="Europe/Moscow",
        now=now,
    )

    assert len(result) == 1
    assert result[0].ambiguous is False
    assert result[0].reminder_at == datetime(2026, 5, 1, 8, 0, tzinfo=ZoneInfo("Europe/Moscow"))


def test_parser_marks_next_week_without_day_as_ambiguous() -> None:
    parser = NaturalLanguageTaskParser()
    now = datetime(2026, 4, 30, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))

    result = parser.parse(
        "На следующей неделе съездить на замер",
        timezone="Europe/Moscow",
        now=now,
    )

    assert result[0].ambiguous is True
    assert result[0].reminder_at is None


def test_parser_extracts_friday_at_8_from_example() -> None:
    parser = NaturalLanguageTaskParser()
    now = datetime(2026, 4, 30, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))

    result = parser.parse(
        "в пятницу созвониться с Игорем прорабом в 8 часов",
        timezone="Europe/Moscow",
        now=now,
    )

    assert result[0].ambiguous is False
    assert result[0].reminder_at == datetime(2026, 5, 1, 8, 0, tzinfo=ZoneInfo("Europe/Moscow"))

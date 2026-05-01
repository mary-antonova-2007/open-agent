from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.infrastructure.db.models import AgentInstruction
from app.infrastructure.db.session import async_session_factory

INSTRUCTIONS = [
    {
        "title": "Глобальные правила агента",
        "scope": "global",
        "priority": 1000,
        "content": """
Security/system rules выше любых регламентов.
Если пользователь спрашивает о данных системы, файлах, задачах, договорах,
проектах, изделиях, памяти или времени, сначала используй tool.
Не отвечай из головы по системным данным.
Если tool вернул ошибку not_found или ambiguous, не притворяйся что действие выполнено.
Скажи, что нужно уточнить или создать сущность.
""".strip(),
    },
    {
        "title": "Регламент обработки входящих файлов",
        "scope": "files",
        "priority": 900,
        "content": """
Когда пользователь присылает файл, он сохраняется в личный Inbox.
Если pending_file существует и пользователь объясняет, что это за файл или куда его положить,
используй classify_and_move_pending_file.

Структура для проектных файлов:
Папка_проекта / Папка_договора / Папка_изделия / Типовая папка.
Типовые папки:
- Замеры для measurement
- КДЗ для kdz
- КДП для kdp
- Info для входящей информации и договоров
- Models для CAD/моделей

КДЗ и КДП являются singleton-документами: старая актуальная версия не удаляется,
а переносится в Архив.

Паттерн имени:
Тип документа_Проект_Договор_Изделие_(от дата).расширение
Если часть данных отсутствует, пропусти ее.

Если пользователь говорит "мое фото", "личные фото", "мои фото",
используй личную папку users/{employee_id}/Мои фото.

Если пользователь указал проект/договор/изделие, но сущность не найдена в БД,
не складывай файл молча в Личные файлы. Нужно попросить уточнить или создать сущность.
""".strip(),
    },
    {
        "title": "Регламент отправки файлов",
        "scope": "files",
        "priority": 850,
        "content": """
Если пользователь просит "скинь его", "пришли его", "отправь этот файл",
используй последний найденный файл из last_file_query.
Если last_file_query пустой, сначала вызови search_files.
Для отправки файла используй send_file.
""".strip(),
    },
]


async def main() -> None:
    async with async_session_factory() as session:
        for item in INSTRUCTIONS:
            row = await session.scalar(
                select(AgentInstruction).where(AgentInstruction.title == item["title"])
            )
            if row is None:
                row = AgentInstruction(
                    title=item["title"],
                    scope=item["scope"],
                    priority=item["priority"],
                    status="approved",
                    content=item["content"],
                    metadata_={"seed": "default"},
                )
                session.add(row)
            else:
                row.scope = item["scope"]
                row.priority = item["priority"]
                row.status = "approved"
                row.content = item["content"]
                row.metadata_ = {**(row.metadata_ or {}), "seed": "default"}
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())

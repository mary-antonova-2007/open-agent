from __future__ import annotations

import uuid

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentState
from app.application.audit_service import AuditService
from app.application.permissions import PermissionDeniedError
from app.application.schemas import EmployeeContext
from app.core.config import get_settings
from app.infrastructure.db.models import AgentRun
from app.infrastructure.llm import ChatMessage, LLMClientError, OpenAICompatibleLLMClient
from app.tools.defaults import build_tool_registry


class AgentOrchestrator:
    """LangGraph-ready orchestrator facade.

    The current implementation is intentionally conservative: it records an agent
    run/audit path and returns controlled responses. LangGraph nodes can be wired
    behind this facade without changing Telegram or API adapters.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()
        self.llm_client = OpenAICompatibleLLMClient()

    async def handle_text(
        self, *, employee: EmployeeContext, text: str, source: str, session_id: int | None = None
    ) -> str:
        state = AgentState(
            employee=employee,
            text=text,
            source=source,
            trace_id=uuid.uuid4().hex,
        )
        state.route = self._route(text)
        state.response = await self._response_for_route(state)
        run = AgentRun(
            trace_id=state.trace_id,
            employee_id=employee.id,
            session_id=session_id,
            status="succeeded",
            route=state.route,
            model=self.settings.llm_model if state.route == "chat" else None,
            finished_at=datetime.now(UTC),
        )
        self.session.add(run)
        await self.session.flush()
        await AuditService(self.session).record(
            action="agent.message.handle",
            result="succeeded",
            actor_employee_id=employee.id,
            trace_id=state.trace_id,
            tool_name=None,
            diff_summary={"route": state.route, "source": source},
        )
        return state.response

    @staticmethod
    def _route(text: str) -> str:
        normalized = text.lower()
        if any(word in normalized for word in ("задач", "напомни", "сделать")):
            return "task"
        if any(
            word in normalized
            for word in ("регламент", "инструкц", "документ")
        ):
            return "knowledge"
        return "chat"

    async def _response_for_route(self, state: AgentState) -> str:
        if state.route == "task":
            return await self._handle_task_route(state)
        if state.route == "knowledge":
            return (
                "Вопрос по базе знаний распознан. RAG будет "
                "применен с учетом прав доступа."
            )
        return await self._handle_chat_route(state)

    async def _handle_chat_route(self, state: AgentState) -> str:
        system_prompt = (
            "Ты внутренний AI Agent компании. Отвечай кратко, по-русски, "
            "без выполнения действий. Если пользователь просит создать задачу, "
            "напоминание, изменить данные, файл или договор, скажи, что запрос "
            "нужно обработать через безопасный tool-flow."
        )
        try:
            response = await self.llm_client.chat(
                [
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(
                        role="user",
                        content=(
                            f"Сотрудник: {state.employee.full_name}. "
                            f"Сообщение: {state.text}"
                        ),
                    ),
                ],
                temperature=0.2,
                max_tokens=128,
            )
        except LLMClientError:
            return (
                "Запрос принят и записан в audit log. "
                "LLM endpoint сейчас недоступен."
            )
        return response or "Запрос принят и записан в audit log."

    async def _handle_task_route(self, state: AgentState) -> str:
        registry = build_tool_registry(self.session)
        try:
            result = await registry.execute(
                name="create_tasks_from_natural_language",
                actor=state.employee,
                payload={"text": state.text},
                trace_id=state.trace_id,
            )
        except PermissionDeniedError:
            return "У вас нет прав на создание задач."
        if result.ok:
            tasks = result.data.get("tasks", [])
            if len(tasks) == 1:
                title = tasks[0].get("title", "задача")
                return f"Создал задачу: {title}."
            return f"Создал задач: {len(tasks)}."
        if result.code == "ambiguous":
            return (
                "Нужно уточнить дату или время задачи. "
                "Напишите конкретный день и время."
            )
        return result.message or (
            "Не удалось создать задачу из сообщения."
        )

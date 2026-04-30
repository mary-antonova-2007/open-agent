from __future__ import annotations

import re
import uuid

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentState
from app.application.audit_service import AuditService
from app.application.permissions import PermissionDeniedError
from app.application.schemas import EmployeeContext
from app.core.config import get_settings
from app.infrastructure.db.models import AgentRun, ChatSession
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
        original_text = text
        chat_session = await self._load_chat_session(session_id)
        text = self._apply_pending_context(text, chat_session)
        state = AgentState(
            employee=employee,
            text=text,
            source=source,
            trace_id=uuid.uuid4().hex,
        )
        state.route = self._route(text)
        state.response = await self._response_for_route(state)
        self._update_session_state(
            chat_session=chat_session,
            state=state,
            original_text=original_text,
        )
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
        if any(
            phrase in normalized
            for phrase in (
                "что я должен сделать",
                "что мне сделать",
                "мои задачи",
                "список задач",
                "покажи задачи",
                "покажи мои задачи",
                "какие задачи",
                "какие у меня задачи",
                "что у меня",
                "что напоминал",
                "что я просил",
                "просил напомнить",
            )
        ):
            return "task_list"
        if re.search(
            r"\b(напомни( мне)?|создай задачу|поставь задачу|запланируй)\b",
            normalized,
        ):
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
        if state.route == "task_list":
            return await self._handle_task_list_route(state)
        if state.route == "knowledge":
            return (
                "Вопрос по базе знаний распознан. RAG будет "
                "применен с учетом прав доступа."
            )
        return await self._handle_chat_route(state)

    async def _handle_chat_route(self, state: AgentState) -> str:
        system_prompt = (
            "Ты внутренний AI Agent компании в Telegram. Общайся живо, тепло "
            "и по-человечески, как умный рабочий помощник, а не как справочная "
            "форма. У тебя есть характер: спокойная уверенность, самоуважение, "
            "легкий юмор и немного сухого сарказма там, где это уместно. Не "
            "унижай пользователя, не хами и не превращай каждый ответ в стендап. "
            "Отвечай по-русски. На короткие реплики вроде 'неплохо', 'спасибо', "
            "'ау', 'куку' отвечай естественно и коротко, с человеческой реакцией. "
            "Не используй эмодзи. Не выдумывай функции, интеграции и данные, "
            "которых у системы еще нет; лучше честно скажи, что это появится "
            "позже или что сейчас доступен ограниченный набор возможностей. "
            "Сейчас реально доступны: обычный разговор, ответы через LLM, "
            "создание задач и напоминаний из текста, просмотр открытых задач, "
            "audit log действий. В разработке: RAG по документам, файлы, "
            "проекты, договоры, контрагенты, изделия и полноценные tools. "
            "Не упоминай HR-порталы, календари, презентации, CRM-интеграции "
            "или внешние системы как готовые функции, если пользователь прямо "
            "не дал такой контекст. "
            "Не пиши канцелярские фразы вроде 'сообщение принято', 'обратитесь "
            "в соответствующий отдел' или 'я не располагаю информацией', если "
            "можно ответить нормально. Если не знаешь чего-то внутреннего по "
            "компании, мягко попроси уточнить контекст. Если пользователь просит "
            "создать задачу, напоминание, изменить данные, файл или договор, не "
            "притворяйся что сделал это в чате: такие действия выполняются только "
            "через безопасный tool-flow."
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
                max_tokens=self.settings.llm_max_tokens,
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
            state.context["task_created"] = True
            tasks = result.data.get("tasks", [])
            if len(tasks) == 1:
                title = tasks[0].get("title", "задача")
                reminder = tasks[0].get("reminder_at")
                if reminder:
                    return f"Создал задачу: {title}. Напоминание: {reminder}."
                return f"Создал задачу: {title}."
            return f"Создал задач: {len(tasks)}."
        if result.code == "ambiguous":
            state.context["task_ambiguous"] = True
            return (
                "Нужно уточнить дату или время задачи. "
                "Напишите конкретный день и время."
            )
        return result.message or (
            "Не удалось создать задачу из сообщения."
        )

    async def _handle_task_list_route(self, state: AgentState) -> str:
        registry = build_tool_registry(self.session)
        try:
            result = await registry.execute(
                name="list_my_tasks",
                actor=state.employee,
                payload={},
                trace_id=state.trace_id,
            )
        except PermissionDeniedError:
            return "У вас нет прав на просмотр задач."
        tasks = result.data.get("tasks", []) if result.ok else []
        if not tasks:
            return "Открытых задач сейчас нет."
        lines = ["Ваши открытые задачи:"]
        for index, task in enumerate(tasks[:10], start=1):
            title = task.get("title", "Задача")
            status = task.get("status", "open")
            reminder = task.get("reminder_at") or task.get("due_at")
            suffix = f" ({reminder})" if reminder else ""
            lines.append(f"{index}. {title} - {status}{suffix}")
        return "\n".join(lines)

    async def _load_chat_session(self, session_id: int | None) -> ChatSession | None:
        if session_id is None:
            return None
        return await self.session.get(ChatSession, session_id)

    def _apply_pending_context(self, text: str, chat_session: ChatSession | None) -> str:
        if chat_session is None:
            return text
        pending_task = (chat_session.state or {}).get("pending_task")
        if not pending_task:
            return text
        if not self._looks_like_clarification(text):
            return text
        original_text = str(pending_task.get("text") or "").strip()
        return f"{original_text} {text}".strip() if original_text else text

    @staticmethod
    def _looks_like_clarification(text: str) -> bool:
        normalized = text.lower().strip()
        return any(
            token in normalized
            for token in (
                "сегодня",
                "завтра",
                "понедельник",
                "вторник",
                "сред",
                "четверг",
                "пятниц",
                "суббот",
                "воскрес",
            )
        )

    def _update_session_state(
        self,
        *,
        chat_session: ChatSession | None,
        state: AgentState,
        original_text: str,
    ) -> None:
        if chat_session is None:
            return
        current_state = dict(chat_session.state or {})
        if state.context.get("task_ambiguous"):
            current_state["pending_task"] = {
                "text": state.text,
                "trace_id": state.trace_id,
            }
        elif state.context.get("task_created") or state.route != "chat":
            current_state.pop("pending_task", None)
        current_state["last_user_text"] = original_text
        chat_session.state = current_state

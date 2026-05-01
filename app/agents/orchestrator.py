from __future__ import annotations

import json
import re
import uuid

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentState
from app.application.audit_service import AuditService
from app.application.entity_service import EntityService
from app.application.file_service import FileService
from app.application.permissions import PermissionDeniedError
from app.application.schemas import EmployeeContext
from app.core.config import get_settings
from app.domain.enums import EntityType
from app.infrastructure.db.models import AgentRun, ChatMessage as DbChatMessage, ChatSession
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
        conversation_context = await self._load_conversation_context(session_id)
        text = self._apply_pending_context(text, chat_session)
        pending_file = (chat_session.state or {}).get("pending_file") if chat_session else None
        state = AgentState(
            employee=employee,
            text=text,
            source=source,
            trace_id=uuid.uuid4().hex,
            context={
                "conversation": conversation_context,
                "current_time": self._current_time_context(employee),
                "session_id": session_id,
                "pending_file": pending_file,
            },
        )
        state.context["intent"] = await self._decide_intent(state)
        state.route = str(state.context["intent"].get("route") or "chat")
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

    async def _decide_intent(self, state: AgentState) -> dict:
        conversation_context = str(state.context.get("conversation") or "").strip()
        system_prompt = (
            "Ты intent planner внутреннего Telegram AI Agent. "
            "Твоя задача - понять последнее сообщение сотрудника и вернуть только JSON, "
            "без markdown и без пояснений. Ты не выполняешь действие сам, а выбираешь "
            "безопасный route/tool для backend.\n\n"
            "Доступные route:\n"
            "- chat: обычный разговор или общий вопрос\n"
            "- conversation_memory: вопрос о текущей истории чата\n"
            "- current_time: вопрос о текущем времени/дате\n"
            "- file_action: пользователь объясняет, что делать с загруженным файлом, "
            "просит структуру папок или ищет файл\n"
            "- task: создать задачу/напоминание из естественного языка\n"
            "- task_list: показать открытые задачи сотрудника\n"
            "- entity: поиск/показ CRM-сущностей или памяти сущности\n"
            "- knowledge: вопрос по регламентам/документам/базе знаний\n\n"
            "Для route=entity выбери tool_name:\n"
            "- search_counterparties\n"
            "- search_projects\n"
            "- search_contracts\n"
            "- search_items\n"
            "- get_project_memory\n"
            "- get_contract_memory\n\n"
            "Поле query - поисковая строка без служебных слов. Если сотрудник просит "
            "'все договоры' или 'какие есть договоры', query должен быть пустой строкой. "
            "Если сотрудник спрашивает 'сколько времени', 'какое сейчас время' "
            "или 'какая дата', выбери route=current_time. Для обычного разговора "
            "Если в истории/контексте есть pending_file и пользователь объясняет, "
            "что это за документ, выбери route=file_action. "
            "query пустой. Верни JSON строго такого вида: "
            "{\"route\":\"...\",\"tool_name\":null,\"query\":\"\",\"reason\":\"...\"}."
        )
        user_content = (
            f"Сотрудник: {state.employee.full_name}\n"
            f"Backend current_time: {state.context.get('current_time')}\n"
            f"Pending file: {state.context.get('pending_file')}\n"
            f"История чата:\n{conversation_context or 'Истории пока нет.'}\n\n"
            f"Последнее сообщение: {state.text}"
        )
        try:
            raw = await self.llm_client.chat(
                [
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=user_content),
                ],
                temperature=0,
                max_tokens=500,
            )
            intent = self._parse_intent_json(raw)
        except LLMClientError:
            return {"route": "chat", "tool_name": None, "query": "", "reason": "llm_unavailable"}
        if intent["route"] not in {
            "chat",
            "conversation_memory",
            "current_time",
            "file_action",
            "task",
            "task_list",
            "entity",
            "knowledge",
        }:
            intent["route"] = "chat"
        return intent

    @staticmethod
    def _parse_intent_json(raw: str) -> dict:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            cleaned = match.group(0)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return {"route": "chat", "tool_name": None, "query": "", "reason": "invalid_json"}
        return {
            "route": str(data.get("route") or "chat"),
            "tool_name": data.get("tool_name"),
            "query": str(data.get("query") or "").strip(),
            "reason": str(data.get("reason") or ""),
        }

    async def _response_for_route(self, state: AgentState) -> str:
        if state.route == "task":
            return await self._handle_task_route(state)
        if state.route == "task_list":
            return await self._handle_task_list_route(state)
        if state.route == "conversation_memory":
            return await self._handle_conversation_memory_route(state)
        if state.route == "current_time":
            return self._handle_current_time_route(state)
        if state.route == "file_action":
            return await self._handle_file_action_route(state)
        if state.route == "entity":
            return await self._handle_entity_route(state)
        if state.route == "knowledge":
            return (
                "Вопрос по базе знаний распознан. RAG будет "
                "применен с учетом прав доступа."
            )
        return await self._handle_chat_route(state)

    def _handle_current_time_route(self, state: AgentState) -> str:
        current_time = state.context.get("current_time") or {}
        return (
            f"Сейчас {current_time.get('local_human')} "
            f"({current_time.get('timezone')}). Без фантазий, это время backend."
        )

    async def _handle_file_action_route(self, state: AgentState) -> str:
        chat_session = await self._load_chat_session(state.context.get("session_id"))
        pending_file = (chat_session.state or {}).get("pending_file") if chat_session else None
        file_service = FileService(self.session)

        lowered = state.text.lower()
        if "структур" in lowered or "папк" in lowered:
            tree = file_service.list_storage_tree()
            if not tree:
                return "Файловая структура пока пустая. Чистый лист, только без романтики."
            return "Текущая структура файлов:\n" + "\n".join(f"- {entry}" for entry in tree[:80])

        if not pending_file:
            return (
                "Файл для обработки сейчас не выбран. Пришли документ в Telegram, "
                "я сохраню его в Inbox и спрошу, куда его положить."
            )

        instruction = await self._classify_file_instruction(state, pending_file)
        entity = await self._resolve_file_entity(state.employee, instruction)
        if entity is None:
            return (
                "Я понял описание файла, но не нашел подходящий проект/договор/изделие в базе. "
                "Сначала создай или уточни сущность, а файл пока лежит в Inbox."
            )

        display_name = self._build_document_filename(instruction)
        version = await file_service.move_inbox_file_to_entity(
            state.employee,
            file_object_id=int(pending_file["file_object_id"]),
            entity_type=entity["entity_type"],
            entity_id=entity["entity_id"],
            file_type=instruction["file_type"],
            display_name=display_name,
            project_title=entity.get("project_title") or instruction.get("project"),
            contract_title=entity.get("contract_title") or instruction.get("contract"),
            item_title=entity.get("item_title") or instruction.get("item"),
            trace_id=state.trace_id,
        )
        if version is None:
            return "Не смог переместить файл: запись или файл на диске не найдены. Inbox, кажется, обиделся."
        if chat_session is not None:
            current_state = dict(chat_session.state or {})
            current_state.pop("pending_file", None)
            chat_session.state = current_state
        return (
            f"Готово. Переложил файл как «{display_name}».\n"
            f"Путь: {version.object_key}"
        )

    async def _classify_file_instruction(self, state: AgentState, pending_file: dict) -> dict:
        system_prompt = (
            "Ты классифицируешь файл для внутреннего файлового агента. "
            "Верни только JSON без markdown. file_type выбери из: "
            "contract, measurement, kdz, kdp, info, model. "
            "doc_type - человекочитаемый тип документа: Договор, Замер, КДЗ, КДП, Info, Model. "
            "Извлеки project, contract, contract_number, item, document_date в формате YYYY-MM-DD, "
            "если они есть. Если данных нет, ставь null."
        )
        user_content = (
            f"Исходное имя файла: {pending_file.get('display_name')}\n"
            f"Инструкция пользователя: {state.text}\n"
            "JSON schema: {\"file_type\":\"contract|measurement|kdz|kdp|info|model\","
            "\"doc_type\":\"...\",\"project\":null,\"contract\":null,"
            "\"contract_number\":null,\"item\":null,\"document_date\":null}"
        )
        try:
            raw = await self.llm_client.chat(
                [
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=user_content),
                ],
                temperature=0,
                max_tokens=700,
            )
            match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            data = json.loads(match.group(0) if match else raw)
        except (LLMClientError, json.JSONDecodeError, AttributeError):
            data = {}
        file_type = str(data.get("file_type") or "info").lower()
        if file_type not in {"contract", "measurement", "kdz", "kdp", "info", "model"}:
            file_type = "info"
        return {
            "file_type": file_type,
            "doc_type": str(data.get("doc_type") or self._default_doc_type(file_type)),
            "project": data.get("project"),
            "contract": data.get("contract"),
            "contract_number": data.get("contract_number"),
            "item": data.get("item"),
            "document_date": data.get("document_date"),
            "original_name": pending_file.get("display_name") or "file",
        }

    async def _resolve_file_entity(
        self, actor: EmployeeContext, instruction: dict
    ) -> dict | None:
        entity_service = EntityService(self.session)
        project_title = instruction.get("project")
        contract_query = instruction.get("contract") or instruction.get("contract_number")
        item_query = instruction.get("item")
        if item_query:
            items = await entity_service.search_items(actor, str(item_query), limit=2)
            if len(items) == 1:
                return {
                    "entity_type": EntityType.item,
                    "entity_id": items[0].id,
                    "item_title": items[0].name,
                    "contract_title": contract_query,
                    "project_title": project_title,
                }
        if contract_query:
            contracts = await entity_service.search_contracts(actor, str(contract_query), limit=2)
            if len(contracts) == 1:
                return {
                    "entity_type": EntityType.contract,
                    "entity_id": contracts[0].id,
                    "contract_title": contracts[0].title,
                    "project_title": project_title,
                }
        if project_title:
            projects = await entity_service.search_projects(actor, str(project_title), limit=2)
            if len(projects) == 1:
                return {
                    "entity_type": EntityType.project,
                    "entity_id": projects[0].id,
                    "project_title": projects[0].title,
                }
        return {"entity_type": EntityType.personal, "entity_id": actor.id, "project_title": "Личные файлы"}

    @staticmethod
    def _build_document_filename(instruction: dict) -> str:
        original = str(instruction.get("original_name") or "file")
        extension = ""
        if "." in original:
            extension = "." + original.rsplit(".", 1)[1].lower()
        parts = [
            instruction.get("doc_type"),
            instruction.get("project"),
            instruction.get("contract_number") or instruction.get("contract"),
            instruction.get("item"),
        ]
        date = instruction.get("document_date")
        stem = "_".join(str(part).strip() for part in parts if part)
        if date:
            stem = f"{stem} (от {date})" if stem else f"Документ (от {date})"
        return f"{stem or original.rsplit('.', 1)[0]}{extension}"

    @staticmethod
    def _default_doc_type(file_type: str) -> str:
        return {
            "contract": "Договор",
            "measurement": "Замер",
            "kdz": "КДЗ",
            "kdp": "КДП",
            "model": "Model",
            "info": "Info",
        }.get(file_type, "Info")

    async def _handle_conversation_memory_route(self, state: AgentState) -> str:
        conversation_context = str(state.context.get("conversation") or "").strip()
        if not conversation_context:
            return (
                "Пока в этой сессии у меня нет сохраненной истории. "
                "Память не магия, а таблица в базе."
            )

        normalized = state.text.lower()
        employee_messages = self._extract_employee_messages(conversation_context)
        if any(phrase in normalized for phrase in ("сообщение назад", "предыдущее сообщение")):
            if not employee_messages:
                return "До этого в истории не вижу твоих сообщений."
            return f"Предыдущее твое сообщение: «{employee_messages[-1]}»."

        focused = self._find_relevant_employee_messages(conversation_context, normalized)
        without_current = [
            message
            for message in focused
            if message.strip().lower() != state.text.strip().lower()
        ]
        if without_current:
            focused = without_current
        if focused:
            return "Ты спрашивал/писал вот это:\n" + "\n".join(
                f"- {message}" for message in focused[:5]
            )

        system_prompt = (
            "Ты отвечаешь только по истории текущего Telegram-чата. "
            "Не здоровайся. Не придумывай. Если пользователь спрашивает, что он "
            "спрашивал или о чем просил, дай короткий конкретный список фактов из "
            "истории. Не пиши 'Агент:' или 'Сотрудник:' в начале ответа."
        )
        user_content = (
            f"История чата:\n{conversation_context}\n\n"
            f"Вопрос пользователя: {state.text}\n\n"
            "Ответь кратко и конкретно."
        )
        try:
            response = await self.llm_client.chat(
                [
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=user_content),
                ],
                temperature=0.2,
                max_tokens=900,
            )
        except LLMClientError:
            return "Историю вижу, но LLM endpoint сейчас недоступен для нормального резюме."
        return self._clean_chat_response(response) or "Историю вижу, но внятный ответ сейчас не собрал."

    async def _handle_entity_route(self, state: AgentState) -> str:
        registry = build_tool_registry(self.session)
        intent = state.context.get("intent") or {}
        tool_name = intent.get("tool_name")
        query = str(intent.get("query") or "").strip()
        try:
            if tool_name == "get_contract_memory":
                return await self._search_and_format_memory(
                    registry=registry,
                    state=state,
                    search_tool="search_contracts",
                    memory_tool="get_contract_memory",
                    collection_key="contracts",
                    entity_label="договор",
                    query=query,
                )
            if tool_name == "get_project_memory":
                return await self._search_and_format_memory(
                    registry=registry,
                    state=state,
                    search_tool="search_projects",
                    memory_tool="get_project_memory",
                    collection_key="projects",
                    entity_label="проект",
                    query=query,
                )
            if tool_name == "search_contracts":
                result = await registry.execute(
                    name="search_contracts",
                    actor=state.employee,
                    payload={"query": query},
                    trace_id=state.trace_id,
                )
                return self._format_search_results(
                    "договоры",
                    result.data.get("contracts", []) if result.ok else [],
                    ("id", "number", "title", "status", "project_id", "counterparty_id"),
                )
            if tool_name == "search_projects":
                result = await registry.execute(
                    name="search_projects",
                    actor=state.employee,
                    payload={"query": query},
                    trace_id=state.trace_id,
                )
                return self._format_search_results(
                    "проекты",
                    result.data.get("projects", []) if result.ok else [],
                    ("id", "title", "status", "responsible_id", "primary_counterparty_id"),
                )
            if tool_name == "search_items":
                result = await registry.execute(
                    name="search_items",
                    actor=state.employee,
                    payload={"query": query},
                    trace_id=state.trace_id,
                )
                return self._format_search_results(
                    "изделия",
                    result.data.get("items", []) if result.ok else [],
                    ("id", "name", "type", "status", "contract_id"),
                )
            if tool_name not in {None, "", "search_counterparties"}:
                return "Я понял, что нужен доступ к базе, но не смог выбрать подходящий безопасный tool."
            result = await registry.execute(
                name="search_counterparties",
                actor=state.employee,
                payload={"query": query},
                trace_id=state.trace_id,
            )
            return self._format_search_results(
                "контрагенты",
                result.data.get("counterparties", []) if result.ok else [],
                ("id", "name", "type", "notes"),
            )
        except PermissionDeniedError:
            return "Нет прав на просмотр этих данных."

    async def _search_and_format_memory(
        self,
        *,
        registry,
        state: AgentState,
        search_tool: str,
        memory_tool: str,
        collection_key: str,
        entity_label: str,
        query: str,
    ) -> str:
        search = await registry.execute(
            name=search_tool,
            actor=state.employee,
            payload={"query": query},
            trace_id=state.trace_id,
        )
        rows = search.data.get(collection_key, []) if search.ok else []
        if not rows:
            return f"Не нашел {entity_label} по запросу «{query or 'все'}»."
        if len(rows) > 1:
            return (
                f"Нашел несколько вариантов, уточни {entity_label}:\n"
                + "\n".join(
                    f"{index}. #{row.get('id')} {row.get('title') or row.get('name')}"
                    for index, row in enumerate(rows[:10], start=1)
                )
            )
        row = rows[0]
        memory = await registry.execute(
            name=memory_tool,
            actor=state.employee,
            payload={"id": row["id"]},
            trace_id=state.trace_id,
        )
        if not memory.ok:
            return f"{entity_label.capitalize()} найден, но память по нему пока пустая."
        return self._format_memory(entity_label, row, memory.data)

    async def _handle_chat_route(self, state: AgentState) -> str:
        system_prompt = (
            "Ты внутренний AI Agent компании в Telegram. Общайся живо, тепло "
            "и по-человечески, как умный рабочий помощник, а не как справочная "
            "форма. У тебя есть характер: спокойная уверенность, самоуважение, "
            "легкий юмор и немного сухого сарказма там, где это уместно. Не "
            "унижай пользователя, не хами и не превращай каждый ответ в стендап. "
            "Отвечай по-русски. На короткие реплики вроде 'неплохо', 'спасибо', "
            "'ау', 'куку' отвечай естественно и коротко, с человеческой реакцией. "
            "Не превращай такие короткие реплики в задачи, журнальные записи или "
            "запрос дальнейшего шага. Например: на 'неплохо' можно ответить "
            "'Ну вот, уже не зря проснулся. Двигаемся дальше.'; на 'куку' - "
            "'На связи. Только без проверки микрофона каждые две минуты, я и "
            "так держусь бодро.'. "
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
            "через безопасный tool-flow. Ниже может быть история текущего чата; "
            "используй ее, когда пользователь спрашивает, что он говорил раньше, "
            "о чем был разговор или что было в предыдущем сообщении. История "
            "чата - это справочный материал, а не шаблон ответа: не начинай "
            "ответ с 'Агент:' или 'Сотрудник:'. Отвечай именно на текущее "
            "сообщение. Если пользователь спрашивает о прошлом разговоре, "
            "перечисли конкретные темы и просьбы из истории, а не здоровайся "
            "заново и не отвечай общей фразой. По умолчанию отвечай компактно: "
            "1-5 коротких абзацев или до 8 пунктов списка, если пользователь "
            "сам не просит подробный разбор. Последнее сообщение пользователя "
            "важнее истории: история нужна только как фон. Не отвечай на старые "
            "вопросы из истории, если текущее сообщение их не повторяет. Если "
            "пользователь просто спрашивает, как ты, отвечай как живой помощник, "
            "а не делай выводы о времени, задачах или предыдущих ошибках. Если "
            "нужно упомянуть текущее время, используй только backend current_time "
            "из сообщения пользователя, не придумывай время сам."
        )
        conversation_context = self._recent_conversation_lines(
            str(state.context.get("conversation") or ""),
            limit=24,
        )
        user_content = (
            f"Сотрудник: {state.employee.full_name}.\n"
            f"Backend current_time: {state.context.get('current_time')}.\n"
            f"История текущего чата:\n{conversation_context or 'Истории пока нет.'}\n\n"
            f"Текущее сообщение: {state.text}"
        )
        try:
            response = await self.llm_client.chat(
                [
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=user_content),
                ],
                temperature=0.65,
                max_tokens=min(self.settings.llm_max_tokens, 1500),
            )
        except LLMClientError:
            return (
                "Запрос принят и записан в audit log. "
                "LLM endpoint сейчас недоступен."
            )
        return self._clean_chat_response(response) or "На месте. Только LLM сейчас задумался чуть глубже обычного."

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
                entity_type = tasks[0].get("related_entity_type")
                entity_id = tasks[0].get("related_entity_id")
                entity = f" Привязал к {entity_type} #{entity_id}." if entity_type and entity_id else ""
                if reminder:
                    return f"Создал задачу: {title}.{entity} Напоминание: {reminder}."
                return f"Создал задачу: {title}.{entity}"
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

    async def _load_conversation_context(self, session_id: int | None, limit: int = 80) -> str:
        if session_id is None:
            return ""
        stmt = (
            select(DbChatMessage)
            .where(DbChatMessage.session_id == session_id)
            .order_by(DbChatMessage.id.desc())
            .limit(limit)
        )
        rows = list((await self.session.scalars(stmt)).all())
        rows.reverse()
        lines = []
        for row in rows:
            text = (row.message_text or "").strip()
            if not text:
                continue
            speaker = "Сотрудник" if row.direction == "in" else "Агент"
            lines.append(f"{speaker}: {text}")
        return "\n".join(lines)

    @staticmethod
    def _clean_chat_response(response: str) -> str:
        cleaned = response.strip()
        cleaned = re.sub(
            r"^(агент|ассистент|сотрудник)\s*:\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        return cleaned.strip()

    @staticmethod
    def _recent_conversation_lines(conversation_context: str, *, limit: int) -> str:
        lines = [line for line in conversation_context.strip().splitlines() if line.strip()]
        return "\n".join(lines[-limit:])

    @staticmethod
    def _current_time_context(employee: EmployeeContext) -> dict[str, str]:
        timezone = employee.timezone or "Europe/Moscow"
        now = datetime.now(ZoneInfo(timezone))
        return {
            "timezone": timezone,
            "iso": now.isoformat(timespec="seconds"),
            "local_human": now.strftime("%Y-%m-%d %H:%M"),
        }

    @staticmethod
    def _extract_entity_query(text: str) -> str:
        cleaned = text.lower()
        cleaned = re.sub(
            r"\b(найди|покажи|открой|дай|расскажи|про|по|память|список|"
            r"все|всех|вся|всю|какие|какой|какая|есть|имеются|существуют|"
            r"мои|мой|мою)\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"\b(контрагент[а-я]*|клиент[а-я]*|поставщик[а-я]*|подрядчик[а-я]*|"
            r"проект[а-я]*|договор[а-я]*|издели[а-я]*)\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"[^\wа-яА-ЯёЁ0-9\- ]+", " ", cleaned)
        return " ".join(cleaned.split())

    @staticmethod
    def _format_search_results(
        label: str,
        rows: list[dict],
        fields: tuple[str, ...],
    ) -> str:
        if not rows:
            return f"В базе пока не нашел подходящие {label}. Нечего показать, кроме честности."
        lines = [f"Нашел {label}:"]
        for index, row in enumerate(rows[:10], start=1):
            parts = []
            for field in fields:
                value = row.get(field)
                if value not in (None, "", [], {}):
                    parts.append(f"{field}: {value}")
            lines.append(f"{index}. " + "; ".join(parts))
        return "\n".join(lines)

    @staticmethod
    def _format_memory(entity_label: str, row: dict, memory: dict) -> str:
        title = row.get("title") or row.get("name") or f"#{row.get('id')}"
        labels = {
            "summary": "Кратко",
            "notes": "Заметки",
            "current_issues": "Текущие вопросы",
            "current_risks": "Риски",
            "important_facts": "Важные факты",
        }
        lines = [f"Память: {entity_label} «{title}»"]
        has_data = False
        for key, label in labels.items():
            value = memory.get(key)
            if value:
                has_data = True
                lines.append(f"{label}: {value}")
        if not has_data:
            lines.append("Пока пусто. Отличный минимализм, но пользы маловато.")
        return "\n".join(lines)

    @staticmethod
    def _extract_employee_messages(conversation_context: str) -> list[str]:
        messages: list[str] = []
        for line in conversation_context.splitlines():
            if line.startswith("Сотрудник:"):
                text = line.removeprefix("Сотрудник:").strip()
                if text:
                    messages.append(text)
        return messages

    @staticmethod
    def _find_relevant_employee_messages(
        conversation_context: str,
        normalized_question: str,
    ) -> list[str]:
        keywords = [
            keyword
            for keyword in re.findall(r"[а-яa-z0-9ё]{4,}", normalized_question)
            if keyword
            not in {
                "спрашивал",
                "спросил",
                "просил",
                "говорили",
                "помнишь",
                "сообщение",
                "предыдущее",
                "тебя",
                "меня",
                "что",
                "какой",
                "какая",
                "какие",
                "какова",
            }
        ]
        if not keywords:
            return []
        messages = AgentOrchestrator._extract_employee_messages(conversation_context)
        return [
            message
            for message in messages
            if any(
                keyword in message.lower() or keyword[:5] in message.lower()
                for keyword in keywords
            )
        ]

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

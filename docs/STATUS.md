# Implementation Status

## Done

- Phase 0 project foundation, Docker Compose, config and quality gate files.
- Phase 1 database schema, RBAC, CRM entities, task/reminder, document/file, audit models.
- Telegram webhook skeleton with employee lookup, idempotency store, chat session and message
  persistence.
- Agent facade with task route connected to typed tools.
- Deterministic Russian natural-language task parser.
- Task, memory, entity search and file metadata services.
- Tool registry with permission and confirmation enforcement.

## Next

- Add integration tests with PostgreSQL testcontainers once Docker/pip are available.
- Add explicit ToolCall persistence around every registry execution.
- Add contract/project ACL filtering beyond RBAC-only checks.
- Add Qdrant-backed RAG ingestion and search.
- Add real Telegram outbound sender for replies/reminders.
- Add MinIO binary adapter for FileService.

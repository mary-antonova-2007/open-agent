# OpenAgentCRM

Local-first AI Agent CRM for Telegram. The project is structured for a production-oriented
implementation: typed tools, RBAC/ACL checks, confirmation flow, audit log, PostgreSQL operational
data, MinIO file storage, Qdrant RAG and Docker Compose deployment.

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

Local Python workflow:

```bash
python3 -m pip install -e ".[dev]"
make quality
```

The current repository contains the Phase 0-1 foundation plus an MVP-safe vertical slice:

- FastAPI app with `/health` and Telegram webhook route.
- SQLAlchemy/Alembic schema for employees, RBAC, CRM entities, tasks, reminders, documents, files,
  chat sessions, agent runs, confirmations and audit logs.
- Application services for permissions, audit, CRM entity search, tasks, project/contract memory and
  file metadata/versioning.
- Typed tool registry with safe/dangerous tool metadata and handlers for task, entity, memory and
  file-read/archive operations.
- Worker and scheduler entrypoints.
- Initial unit/API tests.

## Implemented Vertical Slice

Telegram webhook processing now resolves the employee, persists chat context, creates an agent run,
routes task-like messages, parses simple Russian task/reminder phrasing, creates unambiguous tasks
through typed tools, and writes audit records. Ambiguous relative dates such as "на следующей неделе"
return a clarification response instead of inventing a date.

The deterministic parser is a safe fallback. A local LLM parser can later be added behind the same
`create_tasks_from_natural_language` tool contract.

## Important Safety Rules

- The LLM must not receive direct SQL access.
- The LLM must not receive direct filesystem or MinIO access.
- All side effects go through typed tools.
- Dangerous tools require confirmation.
- All meaningful actions are audit logged.

# OpenAgentCRM Architecture

OpenAgentCRM is a local-first AI agent CRM for Telegram. The system is built so the LLM never
receives direct SQL, filesystem, MinIO or generic HTTP access. All side effects pass through typed
application tools, permission checks, confirmation rules and audit logging.

## Services

- `api`: FastAPI app, healthchecks, Telegram webhook.
- `worker`: Dramatiq jobs for reminders, ingestion and notifications.
- `scheduler`: APScheduler process for periodic reminder scans and digests.
- `postgres`: operational database.
- `redis`: broker, idempotency and transient locks.
- `qdrant`: vector store for ACL-aware RAG.
- `minio`: S3-compatible file storage.

## Layers

- `domain`: enums and business primitives.
- `application`: services, schemas, permission guard, audit.
- `infrastructure`: database models and adapters.
- `tools`: typed tool registry exposed to the agent.
- `agents`: LangGraph-ready orchestration facade.
- `bot`: Telegram adapter.
- `api`: HTTP boundary only.

## Security Invariants

- No raw SQL tool.
- No filesystem tool.
- No direct MinIO access from the LLM.
- All tools declare permissions and danger level.
- Dangerous tools require confirmation before execution.
- All meaningful tool and agent actions are audit logged.

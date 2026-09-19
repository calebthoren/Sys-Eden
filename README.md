# Sys Eden

Local-first Windows system companion, currently in Phase 0 (repository preparation).

Read [AGENTS.md](AGENTS.md) and the versioned canonical documents in [docs](docs/).
The roadmap owns implementation order.

Development requires Python 3.13 and uv:

```powershell
uv sync
uv run pytest
uv run ruff check .
uv run pyright
uv run eden --help
```

Bootstrap configuration uses validated defaults and `EDEN_` environment overrides,
including `EDEN_DATA_DIRECTORY` and `EDEN_STORAGE__MODELS_BUDGET_GB`.
Storage budgets are independent; automatic rebalancing defaults to disabled.
Budget enforcement belongs to subsequent storage work. Configuration loading does
not create directories. Development runtime data belongs in ignored `data/`.
Do not put credentials in configuration or application log messages.

The existing `eden health` command is a stub, pending Milestone 1 database and
provider health checks. `migrations/` is reserved for that milestone's Alembic baseline.

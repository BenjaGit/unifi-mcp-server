# UniFi MCP Server - Claude Instructions

**Version**: v0.2.4 · **Python**: 3.10+ · **Framework**: FastMCP

## Project context

Third-party MCP server exposing the UniFi Network Controller API to AI agents.
Currently being refactored for simplicity — full rewrites of any component are
acceptable if they produce cleaner results. See `docs/TECHNICAL_DEBT.md` for
known architectural issues (monolithic `main.py`, repeated boilerplate, no
connection pooling).

## Refactoring goals

Primary goal is complexity reduction. Prefer fewer abstractions over clever ones.
If a pattern exists purely for extensibility that is not being used, remove it.
The 2,857-line `main.py` monolith and ~186 repetitions of auth/resolve/unwrap
boilerplate are the highest-priority targets.

## Installation & testing

- **Install/update MCP server**: `pipx install -e . --force` (from project root)
- **Run unit tests**: `.venv/bin/python -m pytest tests/unit/` (1,156 tests, 80% minimum coverage for new code)
- **Code quality**: `black src/ tests/` · `isort src/ tests/` · `ruff check src/ tests/ --fix` · `mypy src/`
- **Pre-commit**: `pre-commit run --all-files`
- The local `.venv` is for development/testing only — it does NOT affect the running MCP server
- After code changes: run `pipx install -e . --force` then restart the MCP server

## MCP-specific constraints

- Tool names and descriptions are part of the public interface. Do not rename
  or reword them without explicit instruction.
- Tool input/output schemas are the contract with the caller. Preserve these
  exactly unless told otherwise.
- Handler registration order may matter depending on the SDK. Verify before
  reordering.
- All mutating operations require `confirm=True` and should support dry-run mode.

## Python standards

- Use type hints throughout. No untyped function signatures.
- Prefer flat structure over nested class hierarchies.
- Async where the SDK requires it, sync everywhere else. Do not add async
  speculatively.
- Use httpx for HTTP calls (already in use). Do not mix with requests.
- Use Pydantic models for all data structures.
- Follow TDD: write tests first, then implementation.

## UniFi API patterns

**Legacy vs Integration API** — the two APIs use different field names and ID formats:

| Field | Legacy API (`/api/s/{site}/`) | Integration API (`/integration/v1/sites/{uuid}/`) |
|-------|-------------------------------|---------------------------------------------------|
| Device ID | `_id` (MongoDB ObjectId) | `id` (UUID) |
| MAC address | `mac` | `macAddress` |
| IP address | `ip` | `ipAddress` |
| Device state | `state` (integer: `1`) | `state` (string: `"ONLINE"`) |
| Firmware | `version` | `firmwareVersion` |

**Key rules**:

- Integration API action endpoints require UUID-format IDs — MongoDB ObjectIds will be rejected
- Fetch from `integration_path()` for Integration API actions, NOT `legacy_path()`
- Client actions use MAC addresses directly (no ID translation needed)
- Use `d.get("macAddress", d.get("mac", ""))` pattern for cross-API compatibility
- Integration API device actions only support `RESTART` (uppercase). Locate and upgrade must use legacy `cmd/devmgr`

**API access modes**: Local Gateway (recommended, full features), Cloud V1 (stable, limited), Cloud EA (early access, limited).

## What not to do

- Do not add logging frameworks, metrics, or observability hooks unless asked.
- Do not introduce new dependencies without checking first.
- Do not preserve code structure out of loyalty to the original. If it's
  cleaner to rewrite a module from scratch, do it.
- Do not commit secrets or credentials.

## Subagent delegation

- Use **refactoring-specialist** for structural decisions, complexity reduction,
  and the `main.py` monolith decomposition. It understands code smells, safe
  incremental transformation, and architecture-level refactoring.
- Use **python-pro** for Python-specific implementation quality: type safety,
  async patterns, Pydantic modeling, and httpx client lifecycle design.
- Both agents should read this file before acting.
- Both agents run on Sonnet and have full write access (Read, Write, Edit, Bash, Glob, Grep).

## Context management

Before starting any refactoring phase, write a summary of the current state to
`docs/refactor-state.md`. Include:

- Which modules have been refactored and what changed
- Which tool schemas have been verified as preserved
- Any decisions made and the reasoning behind them
- What remains to be done

Update this file at the end of every subagent session, not just when the
context is full. Treat it as the source of truth if context is lost.

At the start of each new session or after compaction, read
`docs/refactor-state.md` before taking any action.

### Session boundaries

When approaching context limits, stop refactoring. Write current state to
`docs/refactor-state.md`, then stop. Do not attempt to squeeze in more changes
on a nearly full context window. Incomplete changes with lost context are
harder to recover from than a clean stopping point.

## Key resources

- [TECHNICAL_DEBT.md](docs/TECHNICAL_DEBT.md) — Known architectural issues and improvement priorities
- [docs/api/mcp-tools.md](docs/api/mcp-tools.md) — Complete MCP tool reference
- [CONTRIBUTING.md](CONTRIBUTING.md) — Contribution guidelines
- [docs/testing/test-plan.md](docs/testing/test-plan.md) — Testing strategy
- [docs/operations/release-process.md](docs/operations/release-process.md) — Release workflow
- [docs/archive/refactor/REFACTORING_PLAN.md](docs/archive/refactor/REFACTORING_PLAN.md) — Archived refactoring plan (completed 2026-03-16)
- [docs/archive/refactor/REFACTORING_PLAN_OPENCODE.md](docs/archive/refactor/REFACTORING_PLAN_OPENCODE.md) — Archived OpenCode execution addendum (completed 2026-03-16)

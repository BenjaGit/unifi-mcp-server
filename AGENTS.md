# UniFi MCP Server – OpenCode Agent Instructions

This document adapts the canonical rules in `CLAUDE.md` for OpenCode agents powered by OpenAI models. Treat `CLAUDE.md` as policy source; this file mirrors those requirements and adds OpenCode-specific operating guidance. When the two files diverge, follow the stricter rule and raise the mismatch.

## Scope and Precedence

- Applies to every OpenCode/GPT workflow (local CLI, CI bots, GitHub Actions).
- Public contract order: MCP schemas > tests > `CLAUDE.md` > this file > style preferences.
- Never change tool names, descriptions, or schemas unless the repository maintainers explicitly request it.

## Model Routing

- **Planning / analysis**: GPT-5.3 Codex.
- **Implementation / editing**: GPT-5 Codex.
- **Subagents**:
  - `refactoring-specialist` → structural simplification, main.py decomposition.
  - `python-pro` → type safety, httpx lifecycle, Pydantic, test scaffolds.
  - `explore` → broad discovery when file locations are unknown.
- Document subagent use and outcomes; update `docs/refactor-state.md` per `CLAUDE.md`.

## Non-Negotiable MCP Contract

- Tool names/descriptions are public API; do not reword them.
- Tool input/output schemas are immutable contracts; preserve exactly unless instructed otherwise.
- Handler registration order may matter; verify before reordering.
- Every mutating tool requires `confirm=True` and supports `dry_run=True` (default false, no effect); raise `ConfirmationRequiredError` when missing confirm.
- Use `docs/mcp-schemas.json` as schema reference; regenerate only when asked.

## Refactoring Priorities

- Primary goal: reduce complexity, not add abstractions.
- Break up the 2,857-line `src/main.py` monolith; remove redundant auth/resolve/unwrap boilerplate.
- Prefer rewrites over incremental tweaks when it yields clearer code.
- Read `docs/TECHNICAL_DEBT.md` before structural work.

## Python & Testing Standards

- Python ≥3.10, FastMCP framework.
- Type hints everywhere; no untyped defs.
- Async only when required by the SDK; otherwise synchronous.
- `httpx` is the sole HTTP client; no `requests`.
- Model all structured data with Pydantic.
- Follow TDD: write/update tests first, then implementation.
- Commands:
  - `pipx install -e . --force` after changes.
  - `.venv/bin/python -m pytest tests/unit/` (minimum 80% coverage for new code).
  - `black src/ tests/`, `isort src/ tests/`, `ruff check src/ tests/ --fix`, `mypy src/`.
  - `pre-commit run --all-files` before commits or CI handoff.

## UniFi API Invariants

| Field | Legacy `/api/s/{site}/` | Integration `/integration/v1/sites/{uuid}/` |
| --- | --- | --- |
| Device ID | `_id` (ObjectId) | `id` (UUID) |
| MAC | `mac` | `macAddress` |
| IP | `ip` | `ipAddress` |
| State | `state` (int, 1) | `state` ("ONLINE") |
| Firmware | `version` | `firmwareVersion` |

- Integration actions require UUIDs and must use `integration_path()`.
- Client actions use MAC addresses directly (`d.get("macAddress", d.get("mac", ""))`).
- Integration device actions only support `RESTART` (uppercase); locate/upgrade go through legacy `cmd/devmgr`.
- Know API access modes: Local Gateway (full), Cloud V1 (limited), Cloud EA (limited + unstable).

## OpenCode Tool & Git Hygiene

- Use `Read`, `Glob`, `Grep` for inspection; avoid `cat`, `find`, `grep` via Bash unless required.
- Use `apply_patch` or `Edit` for focused updates; keep changes minimal and ASCII unless justified.
- Reserve `Bash` for git/tests/builds; do not shell out for file edits.
- Never run destructive git commands (`reset --hard`, `checkout --`) unless the user explicitly asks.
- Do not amend commits unless instructed; never push without request.
- Do not commit `.env`, credentials, or secrets; warn the user if they try.

## Local MCP Runtime Control (OpenCode)

- Prefer a detached UniFi MCP runtime managed outside OpenCode, then connect OpenCode via remote MCP URL.
- OpenCode config should point UniFi MCP to `http://127.0.0.1:8765/mcp` (`mcp.unifi.type = "remote"`).
- Run UniFi MCP as a user service (`systemd --user`) so it can be restarted without restarting OpenCode.
- Keep runtime credentials in a local user env file (for example `~/.config/opencode/unifi-mcp.env`, mode `600`) instead of embedding them in repo files.
- Provide and use a local control helper (for example `unifi-mcpctl start|stop|restart|status|logs`) for predictable operations.
- After restart, `opencode mcp list` may show a brief transient disconnect; recheck after 1-2 seconds.

## Subagent Delegation Rules

- Invoke `refactoring-specialist` before structural redesigns or when touching `src/main.py` architecture.
- Invoke `python-pro` for complex typing, httpx, or Pydantic work, or when designing new MCP tools/models.
- Include `CLAUDE.md` and `docs/refactor-state.md` context in the agent prompt; summarize outcomes back here if needed.

## Context & Session Management

- Before refactoring: read `docs/refactor-state.md` for latest state.
- After any structural session (human or subagent): update `docs/refactor-state.md` with modules touched, schema checks, decisions, and remaining work.
- When nearing context/token limits, pause, document state, and stop instead of pushing partial edits.

## Pre-Handoff Validation Checklist

1. Tests: `.venv/bin/python -m pytest tests/unit/` (or narrower scope when justified).
2. Quality: `black`, `isort`, `ruff`, `mypy` as listed above.
3. Schema integrity: confirm no tool signature drift; re-compare against `docs/mcp-schemas.json` if editing MCP interfaces.
4. Documentation: update tool references, release notes, or API docs when behavior changes.
5. Install step: rerun `pipx install -e . --force` if package layout changed.

## Key Resources

- `CLAUDE.md` – canonical policy.
- `docs/TECHNICAL_DEBT.md` – architectural problem list.
- `docs/api/mcp-tools.md` – MCP tool reference.
- `docs/testing/test-plan.md` – testing strategy.
- `docs/operations/release-process.md` – release workflow.
- `docs/refactor-state.md` – ongoing refactor log (update per session).
- `docs/archive/refactor/REFACTORING_PLAN.md` – archived refactor scope record (completed 2026-03-16).
- `docs/archive/refactor/REFACTORING_PLAN_OPENCODE.md` – archived OpenCode execution addendum record (completed 2026-03-16).

Keep this adapter current: whenever `CLAUDE.md` changes, mirror the relevant sections here and record the sync date in commit history.

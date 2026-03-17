# Refactoring Execution Plan Addendum — OpenCode/OpenAI

> Archived on 2026-03-16 after addendum completion criteria were satisfied.
> Historical reference only.

## Purpose

This addendum defines how to execute `docs/archive/refactor/REFACTORING_PLAN.md` under OpenCode with OpenAI models. It does not replace the technical scope or ordering from the base plan; it adapts execution, delegation, and validation controls.

## Policy Source and Precedence

- Canonical policy: `CLAUDE.md`
- Runtime adapter: `AGENTS.md`
- Technical phase scope: `docs/archive/refactor/REFACTORING_PLAN.md`
- If guidance conflicts, follow the stricter rule and record the mismatch in `docs/refactor-state.md`.

## Model Routing

- Planning and analysis: GPT-5.3 Codex
- Implementation and edits: GPT-5 Codex
- Subagents:
  - `refactoring-specialist`: structural decomposition, LocalProvider migration, boilerplate collapse
  - `python-pro`: type safety, httpx lifecycle, Pydantic, async correctness, test scaffolds
  - `explore`: broad repo discovery when file ownership is unclear

## Execution Deltas vs Base Plan

1. Keep all Quick Wins and Phases A/B/C unchanged in technical intent.
2. Replace Claude-specific delegation language with the OpenCode subagent routing above.
3. Treat `AGENTS.md` as required companion context for every session.
4. Keep the worktree strategy from the base plan; branch/worktree naming may remain unchanged.

## Required Session Workflow

For each Quick Win/Phase:
1. Read `CLAUDE.md`, `AGENTS.md`, and `docs/refactor-state.md`.
2. Confirm current phase state and pending dependencies.
3. Execute scoped changes only for the current phase.
4. Run the validation suite (see below).
5. Verify MCP interface stability against `docs/mcp-schemas.json` when tool code changes.
6. Update `docs/refactor-state.md` with:
    - Modules touched
    - Schema checks performed
    - Decisions and rationale
    - Remaining work

## Required Skill & Plugin Workflow

> **Policy**: If there is any chance a skill applies, invoke it before acting. The checklist below makes the required skills explicit for each stage of the refactor.

| Phase | Mandatory Skills / Plugins | Purpose |
|-------|----------------------------|---------|
| Global setup | `using-git-worktrees`, `dispatching-parallel-agents`, `subagent-driven-development` | Create isolated worktrees per quick win/phase, route work to the correct subagent, and enforce subagent-driven execution for all chunks. |
| Every coding task | `test-driven-development`, `systematic-debugging` (on failure) | Write/extend tests before implementation and debug failures methodically instead of ad‑hoc edits. |
| Tool or API changes | `FastMCP Development`, `unifi-mcp-tool-builder` | Ensure LocalProvider adoption, lifespan hooks, and MCP tool registration follow FastMCP/UniFi conventions without schema drift. |
| Async/network code | `python-pro` subagent + `verification-before-completion` | Validate connection pooling, RateLimiter wiring, and async file I/O before marking tasks done. |
| Structural refactors | `refactoring-specialist` subagent, `writing-plans` | Decompose `main.py`, design helper modules, and capture implementation steps before editing. |
| Reviews & merges | `requesting-code-review`, `receiving-code-review`, `finishing-a-development-branch` | Drive cross-agent reviews after each phase, handle reviewer feedback, and close out worktrees/branches cleanly. |

**Operational notes**

- Launch `verification-before-completion` prior to claiming any quick win or architecture phase is finished; document evidence (test logs, schema diff) in `docs/refactor-state.md`.
- `subagent-driven-development` remains active throughout Phases A→C; spin up fresh subagents per module batch during the Phase B migration to keep context tight.
- When tests or linters fail, immediately invoke `systematic-debugging` instead of guessing; capture findings in the next `docs/refactor-state.md` entry.
- Before opening PRs or merging branches, follow `finishing-a-development-branch` to ensure validation commands and documentation updates (plan, refactor-state) are complete.

## Validation Standard (OpenCode)

After each completed Quick Win/Phase:
- `.venv/bin/python -m pytest tests/unit/`
- `black src/ tests/`
- `isort src/ tests/`
- `ruff check src/ tests/ --fix`
- `mypy src/`
- `pre-commit run --all-files`

Additional checks:
- No MCP tool name/description/schema drift unless explicitly requested.
- All mutating tools retain `confirm=True` and `dry_run=True` behavior.
- Integration vs legacy API invariants are preserved.

## Delegation Matrix

- QW1 (UUID validation): main session or `python-pro`
- QW2 (audit async safety): `python-pro`
- QW3 (SiteManager rate limiting): `python-pro`
- Phase A (pool/lifespan/re-auth): `python-pro` lead, `refactoring-specialist` review
- Phase B (LocalProvider migration): `refactoring-specialist` lead, `python-pro` review
- Phase C (helpers/boilerplate reduction): `refactoring-specialist` design, `python-pro` async/type review

## Completion Criteria

This addendum is complete when:
- All phases in `docs/REFACTORING_PLAN.md` are finished,
- Validations pass for each phase,
- `docs/refactor-state.md` reflects final architecture state,
- No MCP contract drift is detected.

Archive or delete this addendum alongside the base plan once the refactor is done.

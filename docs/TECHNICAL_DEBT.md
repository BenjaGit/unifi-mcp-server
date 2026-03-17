# Technical Debt

Known architectural and code quality issues identified during the 2026-03-14 codebase audit.
This file now reflects post-refactor status as of 2026-03-16.

**Last reviewed**: 2026-03-16

## Status Summary

- Resolved: 5
- Partially resolved: 2
- Open: 6

---

## Architecture

### `main.py` is a 2,857-line monolith

**Status**: RESOLVED

Every MCP tool signature is duplicated in `src/main.py` as a thin wrapper that calls the real implementation in `src/tools/`. This means adding a single tool requires editing two files, and the file is unwieldy to navigate.

Current state: `src/main.py` is now 365 lines and primarily handles app bootstrap/lifespan/provider registration.

**Potential fix**: FastMCP router/blueprint pattern — register tools directly from their modules without the forwarding layer in `main.py`.

**Effort**: Large — touches every tool registration. Needs a design plan and incremental migration strategy.

### Authenticate + resolve + unwrap boilerplate repeated ~186 times

**Status**: PARTIALLY RESOLVED

Every tool function across the 40 `src/tools/` modules repeats the same pattern: create client, authenticate, resolve site, call endpoint, unwrap response. This is ~15 lines of identical boilerplate per tool.

Current state: `src/tools/_helpers.py` provides shared `resolve()` and `unwrap()` and is adopted in core modules (`clients`, `devices`, `sites`, `settings`, `traffic_rules`), but broader adoption is still pending.

**Potential fix**: Shared client context manager, dependency injection, or a decorator that handles auth/resolve/unwrap and passes a ready-to-use client to the tool function.

**Effort**: Large — same refactor scope as the monolith issue above. Best tackled together.

### New HTTP client + auth per tool invocation (no connection pooling)

**Status**: RESOLVED

Each tool call creates a fresh `httpx.AsyncClient`, authenticates, makes the request, then tears down the client. There is no connection reuse across tool invocations.

Current state: pooled client lifecycle is in place (`src/api/pool.py`) and tools use pooled clients instead of per-call client construction.

**Potential fix**: Singleton or session-scoped client with connection pooling. Needs a client lifecycle redesign — the client must handle token refresh and connection health.

**Effort**: Medium — contained to `src/api/client.py` and the tools that instantiate it, but needs careful async lifecycle management.

## Performance

### `@cached` decorator opens/closes Redis per call

**Status**: OPEN

The caching decorator creates a new Redis connection for every cache check/write. Under load, this adds latency and connection churn.

**Potential fix**: Singleton cache client pattern — initialize once at startup, reuse across calls.

**Effort**: Small-to-medium — mostly isolated to the caching module.

### Synchronous file I/O in `audit.py` blocking event loop

**Status**: RESOLVED

`src/utils/audit.py` performs synchronous file writes for audit logging, which blocks the async event loop.

Current state: writes/reads are offloaded via `anyio.to_thread.run_sync`, and `log_audit` is async.

**Potential fix**: Use `aiofiles` or offload to a thread executor.

**Effort**: Small — straightforward change, low risk. Low priority because the practical impact is minimal (audit writes are fast and infrequent).

## API Parity

### `SiteManagerClient` lacks rate limiting and retry

**Status**: PARTIALLY RESOLVED

The `NetworkClient` has rate limiting and retry logic, but `SiteManagerClient` does not. Under heavy multi-site workloads this could hit API rate limits without graceful handling.

Current state: rate limiting has been added to `SiteManagerClient`. Retry parity with `NetworkClient` is still incomplete.

**Potential fix**: Extract rate-limit/retry into shared middleware or base client class.

**Effort**: Medium — separate feature work, needs testing against real rate limit responses.

## Correctness

### `validate_device_id` rejects UUIDs (only accepts MongoDB ObjectIds)

**Status**: RESOLVED

The validation function only recognizes MongoDB ObjectId format (`^[a-f0-9]{24}$`), but the Integration API uses UUID-format device IDs. Tools that validate IDs before calling Integration API endpoints will reject valid UUIDs.

Current state: validator now accepts both ObjectId and UUID formats.

**Potential fix**: Accept both formats, or determine format based on which API the tool targets (Legacy vs Integration).

**Effort**: Small-to-medium — needs careful analysis of which tools use which API, and the validator is called from many places.

## Code Organization

### Two DPI tool modules with overlapping scope

**Status**: OPEN

Both `src/tools/dpi.py` and `src/tools/dpi_tools.py` exist. The split is not well-defined and creates confusion about where new DPI functionality should go.

**Potential fix**: Merge into a single module during a future DPI enhancement.

**Effort**: Small — minor cleanup.

## CI/CD

### Security scans use `continue-on-error: true`

**Status**: OPEN

Security scan steps in CI don't block the pipeline on failure. A vulnerability could be introduced and merged without CI catching it.

Current state: this is still enabled in CI workflows and remains a policy decision.

**Potential fix**: Policy decision for project owner — remove `continue-on-error` or add a separate required status check that aggregates security results.

**Effort**: Small — configuration change, but requires deciding on acceptable failure modes.

## Testing

### AsyncMock warnings in traffic flow/routing tests

**Status**: RESOLVED

Running `pytest tests/unit/` emits seven `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` messages from the routing and traffic flow suites (for example `tests/unit/tools/test_routing_tools.py::test_get_ddns_status_list_response` plus the `TestGetFlowStatistics`, `TestGetTopFlows`, `TestGetFlowRisks`, and `TestFilterTrafficFlows` classes in `tests/unit/tools/test_traffic_flows_tools.py`). These warnings appear during shutdown because AsyncMocks are created but never awaited in the tests.

Current state: current full unit runs complete cleanly without these warning reports.

**Potential fix**: Await the patched AsyncMocks (or switch the helpers to synchronous mocks when the production code path is sync) so the coroutine lifecycle completes cleanly.

**Effort**: Small — localized to a handful of test cases, but touches several parametrized scenarios.

## MCP UX / Agent Ergonomics

Reference article: [How to Improve Your MCP Server](https://freedium-mirror.cfd/https://medium.com/@shubhampalriwala/how-to-improve-your-mcp-server-da29266062fc)

### No first-class MCP prompt surface for common reasoning workflows

**Status**: OPEN

The server exposes tools and resources, but no FastMCP prompt endpoints for common guided workflows (for example: troubleshooting playbooks, staged analysis prompts, or domain-specific investigation prompts).

**Potential fix**: Add a small curated prompt set in runtime server code for high-value workflows and keep tool invocations for stateful/actions.

**Effort**: Small-to-medium — requires prompt design and validation with real client sessions.

### Tool docstring quality is inconsistent for model-guided tool selection

**Status**: OPEN

Some tools have rich argument/return/error documentation while many still use minimal one-line descriptions. This inconsistency can reduce tool selection reliability and increase retry loops.

**Potential fix**: Standardize tool docstrings with a template: purpose, required args, return shape, common errors, and 1-2 usage examples.

**Effort**: Medium — broad docs sweep across tool modules, but low code risk.

### Response payloads are not consistently optimized for multi-step MCP workflows

**Status**: OPEN

Several endpoints return large or inconsistent payloads where models would benefit from normalized identifiers and compact follow-up context. Token-heavy responses can increase latency/cost and reduce chained-call reliability.

**Potential fix**: Introduce standardized "summary-first" response shapes for high-volume/list tools, with optional detail expansion where needed.

**Effort**: Medium — touches response shaping in multiple tool modules and requires test updates.

# Technical Debt Refactoring Plan — UniFi MCP Server

> Archived on 2026-03-16 after Quick Wins 1-3 and Phases A/B/C were completed.
> Historical reference only.

## Context

The 2026-03-14 audit identified 9 deferred architectural issues (documented in `docs/TECHNICAL_DEBT.md`). This plan addresses the **top 6** — prioritized by impact, grouped into 3 independent quick wins and 3 sequential architecture phases. The architecture phases tackle the interconnected "big three": the main.py monolith, 187× boilerplate, and zero connection pooling.

**Key discovery**: FastMCP 2.14.5 natively supports `LocalProvider` (modular tool registration) and `Depends()` (dependency injection). This means we can use idiomatic FastMCP patterns instead of workarounds.

**Stance** (per CLAUDE.md): Full rewrites of any component are acceptable if they produce cleaner results. Do not preserve code structure out of loyalty to the original. Prefer fewer abstractions over clever ones. Tool names/descriptions and input/output schemas are the public interface — preserve those exactly.

**Working directory**: `/home/benjamin/GitHub/unifi-mcp-server`

**Plan location (archive)**: `docs/archive/refactor/REFACTORING_PLAN.md`.
**Maintenance**: Historical snapshot; no further updates required.

---

## Step 0: Setup (before starting work)

1. Copy this plan to `docs/REFACTORING_PLAN.md` in the repo
2. Add reference in `CLAUDE.md` under Key Resources:
   ```
   - [docs/REFACTORING_PLAN.md](docs/REFACTORING_PLAN.md) - Active refactoring plan — update as work progresses, delete when fully implemented
   ```
3. **Generate MCP schema baseline**: Extract current tool schemas to `docs/mcp-schemas.json` using the MCP schema extractor. This is the immutable reference — any agent can read it to verify tool schemas are preserved without re-scanning the codebase.
4. **Initialize `docs/refactor-state.md`**: Create with initial state (all phases pending, current module inventory, baseline test count).
5. This plan file is a living document — mark phases as completed, note any deviations as they occur

---

## Agent Delegation Strategy

Two custom subagents (defined globally in `~/.claude/agents/`, referenced in CLAUDE.md) divide the work by expertise:

| Agent | Expertise | Assigned Work |
|-------|-----------|---------------|
| **refactoring-specialist** | Structure, complexity reduction, monolith decomposition, architecture-level transformation | Phase B (LocalProvider migration), Phase C step C1 (helper design), structural review of all phases |
| **python-pro** | Type safety, async patterns, Pydantic modeling, httpx client lifecycle | QW2 (async audit), QW3 (rate limiter), Phase A (connection pooling), Phase C step C2-C3 (implementation) |

### Git worktree setup

Worktrees enable parallel agent work on isolated branches. Set up before launching parallel quick wins, clean up after merging.

```bash
# Create worktrees for parallel quick wins
git worktree add ../unifi-mcp-qw1 -b fix/uuid-validation
git worktree add ../unifi-mcp-qw2 -b fix/async-audit
git worktree add ../unifi-mcp-qw3 -b fix/rate-limiting

# After each QW is complete and merged:
git worktree remove ../unifi-mcp-qw1
git worktree remove ../unifi-mcp-qw2
git worktree remove ../unifi-mcp-qw3

# For architecture phases (sequential, so only one worktree at a time):
git worktree add ../unifi-mcp-refactor -b refactor/phase-a-pooling
# After Phase A merge, reuse or recreate for Phase B:
git worktree remove ../unifi-mcp-refactor
git worktree add ../unifi-mcp-refactor -b refactor/phase-b-localprovider
# etc.
```

### Parallelization approach

**Quick wins**: Launch all 3 as parallel worktree agents (one agent per worktree):
- QW1 (UUID fix) → main session or either agent (trivial)
- QW2 (async audit) → **python-pro** in worktree `../unifi-mcp-qw2`
- QW3 (rate limiting) → **python-pro** in worktree `../unifi-mcp-qw3` (or main session — it's small)

**Architecture phases**: Sequential, but delegate by expertise:
- Phase A → **python-pro** designs and implements `pool.py`, lifespan hook, re-auth logic
- Phase B → **refactoring-specialist** leads the monolith decomposition: pilot one module, establish the pattern, then batch-convert remaining 41 modules. Can dispatch sub-worktrees for groups of modules.
- Phase C → **refactoring-specialist** designs `_helpers.py` API; **python-pro** reviews async correctness

### Context management (per CLAUDE.md)

Every agent and session must follow these rules:

1. **Before starting**: Read `docs/refactor-state.md` to understand current state
2. **After completing work**: Update `docs/refactor-state.md` with:
   - Which modules were refactored and what changed
   - Which tool schemas were verified as preserved (cross-check against `docs/mcp-schemas.json`)
   - Decisions made and reasoning
   - What remains to be done
3. **Session boundaries**: When approaching context limits, **stop**. Write state to `docs/refactor-state.md`, then stop. Do not attempt to squeeze in more changes on a nearly full context window.
4. **Schema verification**: After any tool migration, verify against `docs/mcp-schemas.json` that tool names, descriptions, and input/output schemas are unchanged.

### Review checkpoints

After each phase, the *other* agent reviews the work:
- Phase A output → **refactoring-specialist** reviews for structural cleanliness
- Phase B output → **python-pro** reviews for type safety and async correctness
- Both agents read `CLAUDE.md` and `docs/refactor-state.md` before acting

---

## Quick Win 1: Fix `validate_device_id` UUID support (30 min)

**Problem**: `validate_device_id()` only accepts MongoDB ObjectId format (`^[a-f0-9]{24}$`). Integration API endpoints use UUIDs. `execute_port_action()` calls Integration API but validates with ObjectId-only regex — guaranteed failure with valid UUIDs.

**File**: `src/utils/validators.py:101-120`

**Fix**:
```python
_OBJECT_ID_RE = re.compile(r"^[a-f0-9]{24}$")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

def validate_device_id(device_id: str) -> str:
    if not device_id or not isinstance(device_id, str):
        raise ValidationError("Device ID cannot be empty")
    lowered = device_id.lower()
    if not (_OBJECT_ID_RE.match(lowered) or _UUID_RE.match(lowered)):
        raise ValidationError(f"Invalid device ID format: {device_id}")
    return lowered
```

**Tests**: Update `tests/unit/utils/` — add cases for valid UUIDs, mixed-case UUIDs, and invalid formats.

---

## Quick Win 2: Make `audit.py` async-safe (45 min)

**Problem**: `AuditLogger.log_operation()` and `get_recent_operations()` use synchronous `open()` in async code, blocking the event loop on every mutating operation. Called from 26 tool modules.

**File**: `src/utils/audit.py:104-108` (write), `139-155` (read)

**Fix**: Use `anyio.to_thread.run_sync()` (already a transitive dependency via FastMCP) to offload file I/O:

```python
import anyio

async def log_operation(self, ...):
    # ... build audit_record (unchanged) ...
    try:
        await anyio.to_thread.run_sync(self._write_record, json.dumps(audit_record))
    except Exception as e:
        self.logger.error(f"Failed to write audit log: {e}")

def _write_record(self, record_json: str) -> None:
    with open(self.log_file, "a", encoding="utf-8") as f:
        f.write(record_json + "\n")
```

Similarly for `get_recent_operations()` — extract sync read to `_read_records()`, call via `anyio.to_thread.run_sync()`.

**Callers**: `log_audit()` in `src/utils/audit.py` becomes `async def log_audit()`. All 26 tool modules already call it with `await` (it's called inside async functions), so check each callsite — if any call without `await`, add it.

**Tests**: Update audit test mocks to handle async.

---

## Quick Win 3: Add rate limiting to `SiteManagerClient` (30 min)

**Problem**: `NetworkClient` has a `RateLimiter` (token bucket). `SiteManagerClient` has none — can hammer the API without backoff.

**File**: `src/api/site_manager_client.py`

**Fix**: Import and add `RateLimiter` from `src/api/client.py`:
```python
from .client import RateLimiter

class SiteManagerClient:
    def __init__(self, settings):
        ...
        self.rate_limiter = RateLimiter(
            settings.rate_limit_requests, settings.rate_limit_period
        )

    async def get(self, path, ...):
        await self.rate_limiter.acquire()
        ...

    async def post(self, path, ...):
        await self.rate_limiter.acquire()
        ...
```

**Tests**: Add rate limiter tests mirroring existing `UniFiClient` rate limit tests.

---

## Architecture Phase A: Connection Pooling via Lifespan (3-4 hours)

**Problem**: Every tool call creates a fresh `httpx.AsyncClient`, authenticates, makes ONE request, tears everything down. Zero connection reuse.

**Strategy**: Use FastMCP's `lifespan` hook to create long-lived clients at startup and share them via a pool module.

### Step A1: Create `src/api/pool.py`

```python
"""Long-lived client pool for UniFi API connections."""
from __future__ import annotations
from ..config import Settings

_network_client: NetworkClient | None = None
_site_manager_client: SiteManagerClient | None = None

async def initialize(settings: Settings) -> None:
    global _network_client, _site_manager_client
    _network_client = NetworkClient(settings)
    await _network_client.__aenter__()
    await _network_client.authenticate()
    if settings.site_manager_enabled and settings.site_manager_api_key:
        _site_manager_client = SiteManagerClient(settings)
        await _site_manager_client.__aenter__()

async def shutdown() -> None:
    global _network_client, _site_manager_client
    if _network_client:
        await _network_client.close()
        _network_client = None
    if _site_manager_client:
        await _site_manager_client.close()
        _site_manager_client = None

def get_network_client() -> NetworkClient:
    assert _network_client is not None, "Pool not initialized"
    return _network_client

def get_site_manager_client() -> SiteManagerClient:
    assert _site_manager_client is not None, "SiteManager client not initialized"
    return _site_manager_client

def is_initialized() -> bool:
    return _network_client is not None
```

### Step A2: Wire lifespan into main.py

```python
from contextlib import asynccontextmanager
from .api import pool

@asynccontextmanager
async def app_lifespan(server):
    await pool.initialize(settings)
    yield
    await pool.shutdown()

mcp = FastMCP("UniFi MCP Server", lifespan=app_lifespan)
```

### Step A3: Handle re-authentication

Add retry-on-auth-failure to `NetworkClient._request()`:
```python
async def _request(self, method, path, **kwargs):
    try:
        return await self._do_request(method, path, **kwargs)
    except AuthenticationError:
        await self.authenticate()
        return await self._do_request(method, path, **kwargs)
```

### Step A4: Migrate tool modules incrementally

One module at a time, replace:
```python
async with NetworkClient(settings) as client:
    await client.authenticate()
    site = await client.resolve_site(site_id)
```
with:
```python
from ..api.pool import get_network_client, is_initialized

# In tool function:
client = get_network_client()
site = await client.resolve_site(site_id)
```

**Test compatibility**: Add `is_initialized()` guard so tests that mock `NetworkClient` directly still work during migration. Tests create their own mock clients; production uses the pool.

**Files**: `src/api/pool.py` (new), `src/main.py`, `src/api/client.py`, then all 42 `src/tools/*.py` modules incrementally.

---

## Architecture Phase B: Modularize Tool Registration via LocalProvider (4-5 hours)

**Problem**: `main.py` is 2,860 lines of 163 pass-through wrappers duplicating every tool signature.

**Strategy**: FastMCP's `LocalProvider` lets each tool module register its own tools. `main.py` just composes providers.

### Step B1: Pilot with one module (`src/tools/devices.py`)

Convert from:
```python
# In devices.py — functions take settings parameter
async def get_device_details(site_id: str, device_id: str, settings: Settings) -> dict:
    ...
```

To:
```python
# In devices.py — self-registering via LocalProvider
from fastmcp.server.providers import LocalProvider
from ..api.pool import get_network_client

provider = LocalProvider()

@provider.tool()
async def get_device_details(site_id: str, device_id: str) -> dict:
    """Get detailed information for a specific device."""
    client = get_network_client()
    site = await client.resolve_site(validate_site_id(site_id))
    ...
```

Key change: `settings` parameter is removed — tools get the client from the pool.

### Step B2: Update main.py to use providers

```python
from .tools.devices import provider as devices_provider
# ... import all providers ...

mcp = FastMCP(
    "UniFi MCP Server",
    lifespan=app_lifespan,
    providers=[devices_provider, clients_provider, ...],
)
```

Remove the corresponding `@mcp.tool()` wrappers from main.py.

### Step B3: Migrate remaining 41 modules

Mechanical conversion — same pattern for each:
1. Add `from fastmcp.server.providers import LocalProvider` + `provider = LocalProvider()`
2. Replace `async def tool_name(..., settings: Settings)` with `@provider.tool()` + `async def tool_name(...)`
3. Replace `async with NetworkClient(settings)` with `client = get_network_client()`
4. Export `provider` from the module
5. Add provider import in main.py, add to `providers=[]` list
6. Delete corresponding wrapper(s) from main.py

### Step B4: Handle special cases

- **Mutating tools with `annotations`**: Use `@provider.tool(annotations={"destructiveHint": True})`
- **`health_check`**: Stays in main.py (no external module needed)
- **`debug_api_request`**: Stays in main.py (conditionally registered)
- **Resources**: Stay in main.py (only 8, already small)

### Step B5: Update tests

Tests currently call tool functions directly: `await devices_tools.get_device_details(site_id, device_id, settings)`. After refactor, the `settings` parameter is gone. Tests need to:
1. Mock `src.tools.devices.get_network_client` instead of `src.tools.devices.NetworkClient`
2. Remove `settings` from call signatures

This is the largest test change — but mechanical. Can be done module-by-module alongside Step B3.

**Result**: main.py shrinks from ~2,860 lines to ~100 lines (lifespan, provider imports, health_check, debug tool, resources).

---

## Architecture Phase C: Reduce Per-Tool Boilerplate (2-3 hours)

**Depends on**: Phase A (connection pooling) and Phase B (LocalProvider migration).

**Problem**: Even after Phases A and B, each tool still repeats validate → get_client → resolve_site → unwrap_response.

### Step C1: Create `src/tools/_helpers.py`

```python
"""Shared helpers for tool functions."""
from ..api.pool import get_network_client
from ..utils.validators import validate_site_id

async def resolve(site_id: str):
    """Validate site_id, get pooled client, resolve site. Returns (client, site)."""
    client = get_network_client()
    site = await client.resolve_site(validate_site_id(site_id))
    return client, site

def unwrap(response: dict | list) -> list[dict]:
    """Extract data list from API response."""
    if isinstance(response, list):
        return response
    return response.get("data", [])
```

### Step C2: Refactor tool functions

From (~10 lines of boilerplate):
```python
@provider.tool()
async def get_device_details(site_id: str, device_id: str) -> dict:
    device_id = validate_device_id(device_id)
    client = get_network_client()
    site = await client.resolve_site(validate_site_id(site_id))
    response = await client.get(client.legacy_path(site.name, "devices"))
    devices_data = response.get("data", []) if isinstance(response, dict) else response
    ...
```

To (~4 lines):
```python
@provider.tool()
async def get_device_details(site_id: str, device_id: str) -> dict:
    device_id = validate_device_id(device_id)
    client, site = await resolve(site_id)
    for d in unwrap(await client.get(client.legacy_path(site.name, "devices"))):
        ...
```

### Step C3: Module-level loggers

Replace per-function `logger = get_logger(__name__, settings.log_level)` with module-level:
```python
logger = get_logger(__name__)
```
Configure log level once at startup in main.py.

---

## Execution Order

| # | Phase | Agent | Effort | Dependencies | Parallel? |
|---|-------|-------|--------|-------------|-----------|
| 1 | QW1: UUID validation | main session | 30 min | None | Yes — all 3 QWs in parallel worktrees |
| 2 | QW2: Async audit | **python-pro** | 45 min | None | Yes |
| 3 | QW3: Rate limiting | **python-pro** | 30 min | None | Yes |
| 4 | Phase A: Connection pooling | **python-pro** | 3-4 hrs | QWs merged | Sequential from here |
| 5 | Phase B: LocalProvider migration | **refactoring-specialist** | 4-5 hrs | Phase A | Sequential |
| 6 | Phase C: Boilerplate reduction | both agents | 2-3 hrs | Phases A+B | Sequential |

**Quick wins 1-3**: Set up worktrees → launch parallel agents → merge results → remove worktrees.
**Phases A→B→C**: Sequential on a single worktree branch — each builds on the previous. Cross-review after each phase. Remove worktree after final merge.

## Verification

After each phase:
1. `.venv/bin/python -m pytest tests/unit/ -q` → all tests pass
2. `ruff check src/` → no lint errors
3. Verify tool schemas unchanged against `docs/mcp-schemas.json`
4. Update `docs/refactor-state.md` with completed work
5. After Phase A: start server, invoke a tool via MCP, verify connection reuse in logs
6. After Phase B: `wc -l src/main.py` → should be ~100 lines (down from 2,860)
7. After Phase C: spot-check 5 tool modules — boilerplate should be ≤4 lines per function

## Files Summary

| File | Change |
|------|--------|
| `src/utils/validators.py` | QW1: Accept UUID format |
| `src/utils/audit.py` | QW2: Async file I/O via anyio |
| `src/api/site_manager_client.py` | QW3: Add RateLimiter |
| `src/api/pool.py` | **New** — Phase A: connection pool singleton |
| `src/api/client.py` | Phase A: retry-on-auth-failure |
| `src/main.py` | Phase A: lifespan hook; Phase B: replace 163 wrappers with provider imports (~2,760 lines removed) |
| `src/tools/*.py` (42 modules) | Phase B: add LocalProvider + `@provider.tool()`; Phase C: use `resolve()` + `unwrap()` helpers |
| `src/tools/_helpers.py` | **New** — Phase C: shared `resolve()` and `unwrap()` |
| `tests/unit/**` | All phases: update mocks, add new test cases |
| `docs/mcp-schemas.json` | **New** — Step 0: immutable MCP schema baseline for verification |
| `docs/refactor-state.md` | **New** — Step 0: living state document updated every session |
| `docs/REFACTORING_PLAN.md` | **New** — Step 0: this plan, copied into repo |

## Not Addressed (remains in TECHNICAL_DEBT.md)

- Redis cache singleton (cache is not currently used — defer until it's activated)
- DPI module naming (cosmetic — merge during a future DPI feature)
- CI security scan `continue-on-error` (policy decision, not code)

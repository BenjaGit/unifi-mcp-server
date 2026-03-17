"""Events and alarms MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import (
    get_logger,
    log_audit,
    sanitize_log_message,
    validate_confirmation,
    validate_site_id,
)

provider = LocalProvider()

__all__ = ["provider", "list_events", "list_alarms", "archive_all_alarms"]


@provider.tool()
async def list_events(
    site_id: str,
    limit: int = 100,
    event_type: str | None = None,
) -> dict[str, Any]:
    """List events for a site, newest first."""
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)
    limit = min(max(1, limit), 3000)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "stat/event"))
    data: list[dict[str, Any]] = (
        response.get("data", []) if isinstance(response, dict) else (response or [])
    )

    if event_type is not None:
        data = [
            e for e in data if e.get("key", "").startswith(event_type) or e.get("key") == event_type
        ]

    data = data[:limit]
    logger.info(sanitize_log_message(f"Retrieved {len(data)} events for site '{site_id}'"))
    return {"events": data, "count": len(data), "site_id": site_id}


@provider.tool()
async def list_alarms(
    site_id: str,
    limit: int = 100,
    archived: bool | None = None,
) -> dict[str, Any]:
    """List alarms for a site."""
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)
    limit = min(max(1, limit), 3000)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "stat/alarm"))
    data: list[dict[str, Any]] = (
        response.get("data", []) if isinstance(response, dict) else (response or [])
    )

    if archived is not None:
        data = [a for a in data if bool(a.get("archived", False)) == archived]

    data = data[:limit]
    logger.info(sanitize_log_message(f"Retrieved {len(data)} alarms for site '{site_id}'"))
    return {"alarms": data, "count": len(data), "site_id": site_id}


@provider.tool(annotations={"destructiveHint": True})
async def archive_all_alarms(
    site_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Archive all alarms for a site."""
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "archive all alarms", dry_run)
    logger = get_logger(__name__)

    parameters = {"site_id": site_id}
    if dry_run:
        logger.info(sanitize_log_message(f"DRY RUN: Would archive all alarms in site '{site_id}'"))
        await log_audit(
            operation="archive_all_alarms",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_archive": "all alarms", "site_id": site_id}

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    await client.post(
        client.legacy_path(site.name, "cmd/evtmgt"),
        json_data={"cmd": "archive-all-alarms"},
    )

    logger.info(sanitize_log_message(f"Archived all alarms in site '{site_id}'"))
    await log_audit(
        operation="archive_all_alarms",
        parameters=parameters,
        result="success",
        site_id=site_id,
    )
    return {"success": True, "message": "All alarms archived", "site_id": site_id}

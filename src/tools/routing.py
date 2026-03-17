"""DDNS status and routing table MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import get_logger, validate_site_id

provider = LocalProvider()

__all__ = ["provider", "get_ddns_status", "list_active_routes"]


@provider.tool()
async def get_ddns_status(site_id: str) -> dict[str, Any]:
    """Get dynamic DNS (DDNS) status for the site."""
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "stat/dynamicdns"))
    data: list[dict[str, Any]] = (
        response.get("data", []) if isinstance(response, dict) else (response or [])
    )
    logger.info(f"Retrieved {len(data)} DDNS entries for site '{site_id}'")
    return {"ddns": data, "count": len(data), "site_id": site_id}


@provider.tool()
async def list_active_routes(site_id: str) -> dict[str, Any]:
    """List active routing table entries for the site."""
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "stat/routing"))
    data: list[dict[str, Any]] = (
        response.get("data", []) if isinstance(response, dict) else (response or [])
    )
    logger.info(f"Retrieved {len(data)} active routes for site '{site_id}'")
    return {"routes": data, "count": len(data), "site_id": site_id}

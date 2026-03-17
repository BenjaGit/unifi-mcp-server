"""Site health and system info MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import get_logger, sanitize_log_message, validate_site_id

provider = LocalProvider()

__all__ = ["provider", "get_site_health", "get_system_info"]


@provider.tool()
async def get_site_health(site_id: str) -> dict[str, Any]:
    """Get subsystem health for a site."""
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "stat/health"))
    data: list[dict[str, Any]] = (
        response.get("data", []) if isinstance(response, dict) else (response or [])
    )

    logger.info(
        sanitize_log_message(f"Retrieved health for {len(data)} subsystems in site '{site_id}'")
    )
    return {"subsystems": data, "count": len(data), "site_id": site_id}


@provider.tool()
async def get_system_info(site_id: str) -> dict[str, Any]:
    """Get controller system information."""
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "stat/sysinfo"))
    data: list[dict[str, Any]] = (
        response.get("data", []) if isinstance(response, dict) else (response or [])
    )

    info = data[0] if data else {}
    logger.info(
        sanitize_log_message(
            f"Retrieved system info for site '{site_id}': "
            f"version={info.get('version', 'unknown')}"
        )
    )
    return info

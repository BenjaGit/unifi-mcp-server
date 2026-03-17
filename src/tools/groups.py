"""User groups, WLAN groups, and MAC tag MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import get_logger, validate_site_id

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = ["provider", "list_user_groups", "list_wlan_groups", "list_mac_tags"]


@provider.tool()
async def list_user_groups(site_id: str) -> dict[str, Any]:
    """List user bandwidth groups for a site."""
    site_id = validate_site_id(site_id)
    client = get_network_client()
    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "rest/usergroup"))
    data: list[dict[str, Any]] = (
        response.get("data", []) if isinstance(response, dict) else (response or [])
    )
    logger.info(f"Listed {len(data)} user groups for site '{site_id}'")
    return {"groups": data, "count": len(data), "site_id": site_id}


@provider.tool()
async def list_wlan_groups(site_id: str) -> dict[str, Any]:
    """List WLAN groups for a site."""
    site_id = validate_site_id(site_id)
    client = get_network_client()
    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "rest/wlangroup"))
    data: list[dict[str, Any]] = (
        response.get("data", []) if isinstance(response, dict) else (response or [])
    )
    logger.info(f"Listed {len(data)} WLAN groups for site '{site_id}'")
    return {"groups": data, "count": len(data), "site_id": site_id}


@provider.tool()
async def list_mac_tags(site_id: str) -> dict[str, Any]:
    """List MAC address tags for a site."""
    site_id = validate_site_id(site_id)
    client = get_network_client()
    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "rest/tag"))
    data: list[dict[str, Any]] = (
        response.get("data", []) if isinstance(response, dict) else (response or [])
    )
    logger.info(f"Listed {len(data)} MAC tags for site '{site_id}'")
    return {"tags": data, "count": len(data), "site_id": site_id}

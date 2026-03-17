"""RF analysis MCP tools - rogue AP detection and channel info."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import get_logger, validate_site_id

provider = LocalProvider()

__all__ = ["provider", "list_rogue_aps", "list_available_channels"]


@provider.tool()
async def list_rogue_aps(site_id: str, within: int = 24) -> dict[str, Any]:
    """List neighboring and rogue access points detected by the controller."""
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)
    max_age_seconds = within * 3600

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "stat/rogueap"))
    data: list[dict[str, Any]] = (
        response.get("data", []) if isinstance(response, dict) else (response or [])
    )

    filtered = [ap for ap in data if "age" not in ap or ap["age"] <= max_age_seconds]
    rogue_count = sum(1 for ap in filtered if ap.get("is_rogue", False))
    logger.info(f"Found {len(filtered)} neighboring APs ({rogue_count} rogue) for site '{site_id}'")
    return {"aps": filtered, "count": len(filtered), "rogue_count": rogue_count, "site_id": site_id}


@provider.tool()
async def list_available_channels(site_id: str) -> dict[str, Any]:
    """List available RF channels for the site's country/regulatory domain."""
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "stat/current-channel"))
    data: list[dict[str, Any]] = (
        response.get("data", []) if isinstance(response, dict) else (response or [])
    )

    logger.info(f"Retrieved {len(data)} available channels for site '{site_id}'")
    return {"channels": data, "count": len(data), "site_id": site_id}

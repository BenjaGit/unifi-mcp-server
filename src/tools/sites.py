"""Site management MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..models import Site
from ..utils import ResourceNotFoundError, get_logger, validate_limit_offset, validate_site_id
from ._helpers import resolve, unwrap

provider = LocalProvider()

__all__ = ["provider", "get_site_details", "list_all_sites", "list_sites", "get_site_statistics"]


@provider.tool()
async def get_site_details(site_id: str) -> dict[str, Any]:
    """Get detailed site information."""
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    response = await client.get(client.integration_base_path("sites"))
    sites_data = unwrap(response)

    for site_data in sites_data:
        if (
            site_data.get("_id") == site_id
            or site_data.get("id") == site_id
            or site_data.get("name") == site_id
            or site_data.get("internalReference") == site_id
        ):
            site = Site(**site_data)
            logger.info(f"Retrieved site details for {site_id}")
            return site.model_dump()

    raise ResourceNotFoundError("site", site_id)


@provider.tool()
async def list_all_sites(
    limit: int | None = None, offset: int | None = None
) -> list[dict[str, Any]]:
    """List all accessible sites."""
    return await _list_sites_impl(limit=limit, offset=offset)


async def _list_sites_impl(
    limit: int | None = None, offset: int | None = None
) -> list[dict[str, Any]]:
    """Fetch and paginate site list."""
    limit, offset = validate_limit_offset(limit, offset)
    logger = get_logger(__name__)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    endpoint = client.integration_base_path("sites")
    response = await client.get(endpoint)
    sites_data = unwrap(response)

    paginated = sites_data[offset : offset + limit]
    sites = [Site(**s).model_dump() for s in paginated]
    logger.info(f"Retrieved {len(sites)} sites (offset={offset}, limit={limit})")
    return sites


async def list_sites(limit: int | None = None, offset: int | None = None) -> list[dict[str, Any]]:
    """Backward-compatible helper for listing sites."""
    return await _list_sites_impl(limit=limit, offset=offset)


@provider.tool()
async def get_site_statistics(site_id: str) -> dict[str, Any]:
    """Retrieve site-wide statistics."""
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)

    client, site = await resolve(site_id, get_network_client)
    devices_response = await client.get(client.legacy_path(site.name, "devices"))
    clients_response = await client.get(client.legacy_path(site.name, "sta"))
    networks_response = await client.get(client.legacy_path(site.name, "rest/networkconf"))

    devices_data = unwrap(devices_response)
    clients_data = unwrap(clients_response)
    networks_data = unwrap(networks_response)

    ap_count = sum(1 for d in devices_data if d.get("type") == "uap")
    switch_count = sum(1 for d in devices_data if d.get("type") == "usw")
    gateway_count = sum(1 for d in devices_data if d.get("type") in ["ugw", "udm", "uxg"])

    online_devices = sum(1 for d in devices_data if d.get("state") == 1)
    offline_devices = len(devices_data) - online_devices

    wired_clients = sum(1 for c in clients_data if c.get("is_wired") is True)
    wireless_clients = len(clients_data) - wired_clients

    total_tx = sum(c.get("tx_bytes", 0) for c in clients_data)
    total_rx = sum(c.get("rx_bytes", 0) for c in clients_data)

    statistics = {
        "site_id": site_id,
        "devices": {
            "total": len(devices_data),
            "online": online_devices,
            "offline": offline_devices,
            "access_points": ap_count,
            "switches": switch_count,
            "gateways": gateway_count,
        },
        "clients": {
            "total": len(clients_data),
            "wired": wired_clients,
            "wireless": wireless_clients,
        },
        "networks": {"total": len(networks_data)},
        "bandwidth": {
            "total_tx_bytes": total_tx,
            "total_rx_bytes": total_rx,
            "total_bytes": total_tx + total_rx,
        },
    }

    logger.info(f"Retrieved statistics for site '{site_id}'")
    return statistics

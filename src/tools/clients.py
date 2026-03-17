"""Client management MCP tools."""

import asyncio
from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..models import Client
from ..utils import ResourceNotFoundError, get_logger, sanitize_log_message, validate_mac_address
from ._helpers import resolve, unwrap

provider = LocalProvider()

__all__ = [
    "provider",
    "get_client_details",
    "get_client_statistics",
    "list_active_clients",
    "search_clients",
]


@provider.tool()
async def get_client_details(site_id: str, client_mac: str) -> dict[str, Any]:
    """Get detailed information for a specific client."""
    client_mac = validate_mac_address(client_mac)
    logger = get_logger(__name__)

    client, site = await resolve(site_id, get_network_client)

    active_response = await client.get(client.legacy_path(site.name, "sta"))
    for client_data in unwrap(active_response):
        mac = client_data.get("mac")
        if not mac:
            continue
        if validate_mac_address(mac) == client_mac:
            client_obj = Client(**client_data)
            logger.info(sanitize_log_message(f"Retrieved client details for {client_mac}"))
            return client_obj.model_dump()

    alluser_response = await client.get(client.legacy_path(site.name, "stat/alluser"))
    for client_data in unwrap(alluser_response):
        mac = client_data.get("mac")
        if not mac:
            continue
        if validate_mac_address(mac) == client_mac:
            client_obj = Client(**client_data)
            logger.info(sanitize_log_message(f"Retrieved client details for {client_mac}"))
            return client_obj.model_dump()

    raise ResourceNotFoundError("client", client_mac)


@provider.tool()
async def get_client_statistics(site_id: str, client_mac: str) -> dict[str, Any]:
    """Retrieve bandwidth and connection statistics for a client."""
    client_mac = validate_mac_address(client_mac)
    logger = get_logger(__name__)

    client, site = await resolve(site_id, get_network_client)
    response = await client.get(client.legacy_path(site.name, "sta"))

    for client_data in unwrap(response):
        mac = client_data.get("mac")
        if not mac:
            continue
        if validate_mac_address(mac) == client_mac:
            stats = {
                "mac": client_mac,
                "tx_bytes": client_data.get("tx_bytes", 0),
                "rx_bytes": client_data.get("rx_bytes", 0),
                "tx_packets": client_data.get("tx_packets", 0),
                "rx_packets": client_data.get("rx_packets", 0),
                "tx_rate": client_data.get("tx_rate"),
                "rx_rate": client_data.get("rx_rate"),
                "signal": client_data.get("signal"),
                "rssi": client_data.get("rssi"),
                "noise": client_data.get("noise"),
                "uptime": client_data.get("uptime", 0),
                "is_wired": client_data.get("is_wired", False),
            }
            logger.info(sanitize_log_message(f"Retrieved statistics for client {client_mac}"))
            return stats

    raise ResourceNotFoundError("client", client_mac)


@provider.tool()
async def list_active_clients(site_id: str) -> list[dict[str, Any]]:
    """List currently connected clients."""
    logger = get_logger(__name__)

    client, site = await resolve(site_id, get_network_client)
    response = await client.get(client.legacy_path(site.name, "sta"))
    clients = [Client(**c).model_dump() for c in unwrap(response)]

    logger.info(
        sanitize_log_message(f"Retrieved {len(clients)} active clients for site '{site_id}'")
    )
    return clients


@provider.tool()
async def search_clients(site_id: str, query: str) -> list[dict[str, Any]]:
    """Search clients by MAC, IP, or hostname."""
    logger = get_logger(__name__)

    client, site = await resolve(site_id, get_network_client)
    active_response, alluser_response = await asyncio.gather(
        client.get(client.legacy_path(site.name, "sta")),
        client.get(client.legacy_path(site.name, "stat/alluser")),
    )

    active_data = unwrap(active_response)
    alluser_data = unwrap(alluser_response)

    clients_by_mac = {mac: c for c in alluser_data if (mac := c.get("mac"))}
    clients_by_mac.update({mac: c for c in active_data if (mac := c.get("mac"))})
    clients_data = list(clients_by_mac.values())

    query_lower = query.lower()
    filtered = [
        c
        for c in clients_data
        if query_lower in (c.get("mac") or "").lower()
        or query_lower in (c.get("ip") or "").lower()
        or query_lower in (c.get("hostname") or "").lower()
        or query_lower in (c.get("name") or "").lower()
    ]

    clients = [Client(**c).model_dump() for c in filtered]
    logger.info(
        sanitize_log_message(f"Found {len(clients)} clients matching '{query}' in site '{site_id}'")
    )
    return clients

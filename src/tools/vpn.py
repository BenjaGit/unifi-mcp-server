"""VPN management MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..models.vpn import VPNServer, VPNTunnel
from ..utils import get_logger, validate_limit_offset, validate_site_id

provider = LocalProvider()

__all__ = ["provider", "list_vpn_tunnels", "list_vpn_servers"]


@provider.tool()
async def list_vpn_tunnels(
    site_id: str,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    """List all site-to-site VPN tunnels in a site (read-only).

    Args:
        site_id: Site identifier
        settings: Application settings
        limit: Maximum number of tunnels to return
        offset: Number of tunnels to skip

    Returns:
        List of VPN tunnel dictionaries
    """
    site_id = validate_site_id(site_id)
    limit, offset = validate_limit_offset(limit, offset)
    logger = get_logger(__name__)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    response = await client.get(client.integration_path(site.uuid, "vpn/site-to-site-tunnels"))
    tunnels_data: list[dict[str, Any]] = (
        response if isinstance(response, list) else response.get("data", [])
    )

    paginated = tunnels_data[offset : offset + limit]

    logger.info(f"Retrieved {len(paginated)} VPN tunnels for site '{site_id}'")
    return [VPNTunnel(**tunnel).model_dump() for tunnel in paginated]


@provider.tool()
async def list_vpn_servers(
    site_id: str,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    """List all VPN servers in a site (read-only).

    Args:
        site_id: Site identifier
        settings: Application settings
        limit: Maximum number of servers to return
        offset: Number of servers to skip

    Returns:
        List of VPN server dictionaries
    """
    site_id = validate_site_id(site_id)
    limit, offset = validate_limit_offset(limit, offset)
    logger = get_logger(__name__)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    response = await client.get(client.integration_path(site.uuid, "vpn/servers"))
    servers_data: list[dict[str, Any]] = (
        response if isinstance(response, list) else response.get("data", [])
    )

    paginated = servers_data[offset : offset + limit]

    logger.info(f"Retrieved {len(paginated)} VPN servers for site '{site_id}'")
    return [VPNServer(**server).model_dump() for server in paginated]

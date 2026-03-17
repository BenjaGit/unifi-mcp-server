"""Site-to-Site VPN management MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..models.vpn import SiteToSiteVPN
from ..utils import ResourceNotFoundError, get_logger, validate_confirmation, validate_site_id

provider = LocalProvider()

__all__ = [
    "provider",
    "list_site_to_site_vpns",
    "get_site_to_site_vpn",
    "update_site_to_site_vpn",
]


@provider.tool()
async def list_site_to_site_vpns(site_id: str) -> list[dict[str, Any]]:
    """List all site-to-site VPN configurations."""
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "rest/networkconf"))
    networks = response if isinstance(response, list) else response.get("data", [])
    vpns = [network for network in networks if network.get("purpose") == "site-vpn"]

    logger.info(f"Retrieved {len(vpns)} site-to-site VPNs")
    return [SiteToSiteVPN(**vpn).model_dump() for vpn in vpns]


@provider.tool()
async def get_site_to_site_vpn(site_id: str, vpn_id: str) -> dict[str, Any]:
    """Get details for a specific site-to-site VPN."""
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "rest/networkconf"))
    networks = response if isinstance(response, list) else response.get("data", [])

    for network in networks:
        if network.get("_id") == vpn_id and network.get("purpose") == "site-vpn":
            logger.info(f"Retrieved VPN {vpn_id}")
            return SiteToSiteVPN(**network).model_dump()

    raise ResourceNotFoundError("vpn", vpn_id)


@provider.tool()
async def update_site_to_site_vpn(
    site_id: str,
    vpn_id: str,
    name: str | None = None,
    enabled: bool | None = None,
    ipsec_peer_ip: str | None = None,
    remote_vpn_subnets: list[str] | None = None,
    x_ipsec_pre_shared_key: str | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update a site-to-site VPN configuration (requires confirm=True)."""
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "update site-to-site vpn", dry_run)
    logger = get_logger(__name__)

    updates: dict[str, Any] = {}
    if name is not None:
        updates["name"] = name
    if enabled is not None:
        updates["enabled"] = enabled
    if ipsec_peer_ip is not None:
        updates["ipsec_peer_ip"] = ipsec_peer_ip
    if remote_vpn_subnets is not None:
        updates["remote_vpn_subnets"] = remote_vpn_subnets
    if x_ipsec_pre_shared_key is not None:
        updates["x_ipsec_pre_shared_key"] = x_ipsec_pre_shared_key

    if dry_run:
        return {"dry_run": True, "vpn_id": vpn_id, "updates": updates}

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    response = await client.get(client.legacy_path(site.name, f"rest/networkconf/{vpn_id}"))
    current = response if isinstance(response, dict) and "_id" in response else None
    if not current:
        response_list = response if isinstance(response, list) else response.get("data", [])
        current = response_list[0] if response_list else None
    if not current or current.get("purpose") != "site-vpn":
        raise ResourceNotFoundError("vpn", vpn_id)

    payload = {**current, **updates}
    await client.put(client.legacy_path(site.name, f"rest/networkconf/{vpn_id}"), json_data=payload)
    logger.info(f"Updated VPN {vpn_id}")
    return {"success": True, "vpn_id": vpn_id, "updates": updates}

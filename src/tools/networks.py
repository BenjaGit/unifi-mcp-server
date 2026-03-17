"""Network information MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import ResourceNotFoundError, get_logger, validate_limit_offset, validate_site_id

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = [
    "provider",
    "get_network_details",
    "list_vlans",
    "get_subnet_info",
    "get_network_references",
    "get_network_statistics",
]


@provider.tool()
async def get_network_details(site_id: str, network_id: str) -> dict[str, Any]:
    """Get detailed network configuration.

    Args:
        site_id: Site identifier
        network_id: Network identifier
        settings: Application settings

    Returns:
        Network details dictionary

    Raises:
        ResourceNotFoundError: If network not found
    """
    site_id = validate_site_id(site_id)

    client = get_network_client()
    site = await client.resolve_site(site_id)

    try:
        response = await client.get(client.integration_path(site.uuid, f"networks/{network_id}"))
        data = response if isinstance(response, dict) else {}
        if not data:
            raise ResourceNotFoundError("network", network_id)

        logger.info(f"Retrieved network details for {network_id}")
        return data
    except Exception as e:
        if "404" in str(e) or "not found" in str(e).lower():
            raise ResourceNotFoundError("network", network_id) from e
        raise


@provider.tool()
async def list_vlans(
    site_id: str,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    """List all VLANs in a site.

    Args:
        site_id: Site identifier
        settings: Application settings
        limit: Maximum number of VLANs to return
        offset: Number of VLANs to skip

    Returns:
        List of VLAN dictionaries
    """
    site_id = validate_site_id(site_id)
    limit, offset = validate_limit_offset(limit, offset)

    client = get_network_client()
    site = await client.resolve_site(site_id)

    response = await client.get(client.integration_path(site.uuid, "networks"))
    if isinstance(response, list):
        networks_data: list[dict[str, Any]] = [n for n in response if isinstance(n, dict)]
    elif isinstance(response, dict):
        data = response.get("data", [])
        networks_data = [n for n in data if isinstance(n, dict)] if isinstance(data, list) else []
    else:
        networks_data = []

    logger.debug(f"Found {len(networks_data)} networks before pagination")

    paginated = networks_data[offset : offset + limit]

    logger.info(f"Retrieved {len(paginated)} VLANs for site '{site_id}'")
    return paginated


@provider.tool()
async def get_subnet_info(site_id: str, network_id: str) -> dict[str, Any]:
    """Get subnet and DHCP information for a network."""

    site_id = validate_site_id(site_id)

    client = get_network_client()
    site = await client.resolve_site(site_id)

    try:
        data = await client.get(client.integration_path(site.uuid, f"networks/{network_id}"))
    except Exception as e:
        if "404" in str(e) or "not found" in str(e).lower():
            raise ResourceNotFoundError("network", network_id) from e
        raise

    if not data or not isinstance(data, dict):
        raise ResourceNotFoundError("network", network_id)

    ipv4 = data.get("ipv4Configuration", {}) or {}
    dhcp = ipv4.get("dhcpConfiguration", {}) or {}
    ip_range = dhcp.get("ipAddressRange", {}) or {}
    dns_overrides = dhcp.get("dnsServerIpAddressesOverride", []) or []

    host_ip = ipv4.get("hostIpAddress")
    prefix_len = ipv4.get("prefixLength")
    ip_subnet = f"{host_ip}/{prefix_len}" if host_ip and prefix_len else None

    subnet_info: dict[str, Any] = {
        "network_id": data.get("id", network_id),
        "name": data.get("name"),
        "ip_subnet": ip_subnet,
        "vlan_id": data.get("vlanId"),
        "dhcpd_enabled": dhcp.get("mode") == "SERVER",
        "dhcpd_start": ip_range.get("start"),
        "dhcpd_stop": ip_range.get("stop"),
        "dhcpd_leasetime": dhcp.get("leaseTimeSeconds"),
        "dhcpd_dns_1": dns_overrides[0] if len(dns_overrides) > 0 else None,
        "dhcpd_dns_2": dns_overrides[1] if len(dns_overrides) > 1 else None,
        "dhcpd_dns_3": dns_overrides[2] if len(dns_overrides) > 2 else None,
        "dhcpd_dns_4": dns_overrides[3] if len(dns_overrides) > 3 else None,
        "dhcpd_gateway": ipv4.get("hostIpAddress"),
        "domain_name": dhcp.get("domainName"),
    }
    logger.info(f"Retrieved subnet info for network {network_id}")
    return subnet_info


@provider.tool()
async def get_network_references(site_id: str, network_id: str) -> dict[str, Any]:
    """Get resources that reference a network (WiFi, clients, devices, etc.).

    Useful for checking dependencies before modifying or deleting a network.

    Args:
        site_id: Site identifier
        network_id: Network identifier
        settings: Application settings

    Returns:
        Dictionary with network_id, references list, and total_references count

    Raises:
        ResourceNotFoundError: If network not found
    """
    site_id = validate_site_id(site_id)

    client = get_network_client()
    site = await client.resolve_site(site_id)

    try:
        data = await client.get(
            client.integration_path(site.uuid, f"networks/{network_id}/references")
        )
    except Exception as e:
        if "404" in str(e) or "not found" in str(e).lower():
            raise ResourceNotFoundError("network", network_id) from e
        raise

    if not data:
        raise ResourceNotFoundError("network", network_id)

    resources = data.get("referenceResources", []) if isinstance(data, dict) else []

    references = [
        {
            "resource_type": r.get("resourceType"),
            "count": r.get("referenceCount", 0),
            "ids": [ref.get("referenceId") for ref in r.get("references", [])],
        }
        for r in resources
    ]

    total = sum(r["count"] for r in references)
    logger.info(f"Network {network_id} has {total} references across {len(references)} types")

    return {
        "network_id": network_id,
        "references": references,
        "total_references": total,
    }


@provider.tool()
async def get_network_statistics(site_id: str) -> dict[str, Any]:
    """Retrieve network usage statistics for a site.

    Args:
        site_id: Site identifier
        settings: Application settings

    Returns:
        Network statistics dictionary
    """
    site_id = validate_site_id(site_id)

    client = get_network_client()
    site = await client.resolve_site(site_id)

    networks_response = await client.get(client.integration_path(site.uuid, "networks"))
    networks_data = (
        networks_response
        if isinstance(networks_response, list)
        else networks_response.get("data", [])
    )

    clients_response = await client.get(client.legacy_path(site.name, "sta"))
    clients_data = (
        clients_response.get("data", []) if isinstance(clients_response, dict) else clients_response
    )

    network_stats = []
    for network in networks_data:
        network_id = network.get("id")
        vlan_id = network.get("vlanId")

        clients_on_network = [c for c in clients_data if c.get("vlan") == vlan_id]

        total_tx = sum(c.get("tx_bytes", 0) for c in clients_on_network)
        total_rx = sum(c.get("rx_bytes", 0) for c in clients_on_network)

        network_stats.append(
            {
                "network_id": network_id,
                "name": network.get("name"),
                "vlan_id": vlan_id,
                "client_count": len(clients_on_network),
                "total_tx_bytes": total_tx,
                "total_rx_bytes": total_rx,
                "total_bytes": total_tx + total_rx,
            }
        )

    logger.info(f"Retrieved network statistics for site '{site_id}'")
    return {"site_id": site_id, "networks": network_stats}

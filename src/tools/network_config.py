"""Network configuration MCP tools."""

import ipaddress
from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import (
    ResourceNotFoundError,
    ValidationError,
    get_logger,
    log_audit,
    validate_confirmation,
    validate_site_id,
)

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = ["provider", "create_network", "update_network", "delete_network"]


def _parse_subnet(subnet: str) -> tuple[str, int]:
    """Parse CIDR notation into gateway IP and prefix length.

    Uses the first usable host address as the gateway IP,
    which matches UniFi's default behavior.

    Args:
        subnet: CIDR notation (e.g., "192.168.1.0/24")

    Returns:
        Tuple of (host_ip, prefix_length)

    Raises:
        ValidationError: If subnet is invalid
    """
    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError as e:
        raise ValidationError(f"Invalid subnet '{subnet}': {e}") from e

    # First usable host = gateway IP (UniFi convention)
    host_ip = str(network.network_address + 1)
    return host_ip, network.prefixlen


def _build_network_payload(
    *,
    name: str | None = None,
    vlan_id: int | None = None,
    subnet: str | None = None,
    purpose: str | None = None,
    dhcp_enabled: bool | None = None,
    dhcp_start: str | None = None,
    dhcp_stop: str | None = None,
    dhcp_dns_1: str | None = None,
    dhcp_dns_2: str | None = None,
    dhcp_dns_3: str | None = None,
    dhcp_dns_4: str | None = None,
    domain_name: str | None = None,
) -> dict[str, Any]:
    """Build Integration API network payload from tool parameters.

    Only includes fields that are explicitly provided (not None),
    so this works for both create (all required fields set) and
    partial update (only changed fields set).
    """
    payload: dict[str, Any] = {}

    if name is not None:
        payload["name"] = name
    if vlan_id is not None:
        payload["vlanId"] = vlan_id
    if purpose is not None:
        # Integration API uses uppercase purpose values
        payload["purpose"] = purpose.upper().replace("-", "_")

    # Build ipv4Configuration if any IP-related fields are set
    ipv4_config: dict[str, Any] = {}

    if subnet is not None:
        host_ip, prefix_length = _parse_subnet(subnet)
        ipv4_config["hostIpAddress"] = host_ip
        ipv4_config["prefixLength"] = prefix_length

    # Build DHCP configuration
    dhcp_config: dict[str, Any] = {}

    if dhcp_enabled is not None:
        dhcp_config["mode"] = "SERVER" if dhcp_enabled else "NONE"

    if dhcp_start is not None or dhcp_stop is not None:
        ip_range: dict[str, str] = {}
        if dhcp_start is not None:
            ip_range["start"] = dhcp_start
        if dhcp_stop is not None:
            ip_range["stop"] = dhcp_stop
        dhcp_config["ipAddressRange"] = ip_range

    # Collect DNS overrides
    dns_servers = [
        dns for dns in [dhcp_dns_1, dhcp_dns_2, dhcp_dns_3, dhcp_dns_4] if dns is not None
    ]
    if dns_servers:
        dhcp_config["dnsServerIpAddressesOverride"] = dns_servers

    if domain_name is not None:
        dhcp_config["domainName"] = domain_name

    if dhcp_config:
        ipv4_config["dhcpConfiguration"] = dhcp_config

    if ipv4_config:
        payload["ipv4Configuration"] = ipv4_config

    return payload


@provider.tool(annotations={"destructiveHint": True})
async def create_network(
    site_id: str,
    name: str,
    vlan_id: int,
    subnet: str,
    purpose: str = "corporate",
    dhcp_enabled: bool = True,
    dhcp_start: str | None = None,
    dhcp_stop: str | None = None,
    dhcp_dns_1: str | None = None,
    dhcp_dns_2: str | None = None,
    dhcp_dns_3: str | None = None,
    dhcp_dns_4: str | None = None,
    domain_name: str | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create a new network/VLAN.

    Uses the official Integration API: POST /v1/sites/{id}/networks

    Args:
        site_id: Site identifier
        name: Network name
        vlan_id: VLAN ID (1-4094)
        subnet: Network subnet in CIDR notation (e.g., "192.168.1.0/24")
        settings: Application settings
        purpose: Network purpose (corporate, guest, vlan-only)
        dhcp_enabled: Enable DHCP server
        dhcp_start: DHCP range start IP
        dhcp_stop: DHCP range stop IP
        dhcp_dns_1: Primary DNS server
        dhcp_dns_2: Secondary DNS server
        dhcp_dns_3: Tertiary DNS server
        dhcp_dns_4: Quaternary DNS server
        domain_name: Domain name for DHCP
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't create the network

    Returns:
        Created network dictionary or dry-run result

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ValidationError: If validation fails
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "network configuration operation", dry_run)

    # Validate VLAN ID
    if not 1 <= vlan_id <= 4094:
        raise ValidationError(f"Invalid VLAN ID {vlan_id}. Must be between 1 and 4094")

    # Validate purpose
    valid_purposes = ["corporate", "guest", "vlan-only", "wan"]
    if purpose not in valid_purposes:
        raise ValidationError(f"Invalid purpose '{purpose}'. Must be one of: {valid_purposes}")

    # Validate subnet format (also validates via ipaddress module)
    if "/" not in subnet:
        raise ValidationError(f"Invalid subnet '{subnet}'. Must be in CIDR notation")

    # Build Integration API payload
    network_data = _build_network_payload(
        name=name,
        vlan_id=vlan_id,
        subnet=subnet,
        purpose=purpose,
        dhcp_enabled=dhcp_enabled,
        dhcp_start=dhcp_start,
        dhcp_stop=dhcp_stop,
        dhcp_dns_1=dhcp_dns_1,
        dhcp_dns_2=dhcp_dns_2,
        dhcp_dns_3=dhcp_dns_3,
        dhcp_dns_4=dhcp_dns_4,
        domain_name=domain_name,
    )

    # Log parameters for audit
    parameters = {
        "site_id": site_id,
        "name": name,
        "vlan_id": vlan_id,
        "subnet": subnet,
        "purpose": purpose,
        "dhcp_enabled": dhcp_enabled,
        "dhcp_start": dhcp_start,
        "dhcp_stop": dhcp_stop,
    }

    if dry_run:
        logger.info(f"DRY RUN: Would create network '{name}' in site '{site_id}'")
        await log_audit(
            operation="create_network",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_create": network_data}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)

        response = await client.post(
            client.integration_path(site.uuid, "networks"), json_data=network_data
        )
        created_network = response if isinstance(response, dict) else {}

        logger.info(f"Created network '{name}' in site '{site_id}'")
        await log_audit(
            operation="create_network",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return created_network

    except Exception as e:
        logger.error(f"Failed to create network '{name}': {e}")
        await log_audit(
            operation="create_network",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def update_network(
    site_id: str,
    network_id: str,
    name: str | None = None,
    vlan_id: int | None = None,
    subnet: str | None = None,
    purpose: str | None = None,
    dhcp_enabled: bool | None = None,
    dhcp_start: str | None = None,
    dhcp_stop: str | None = None,
    dhcp_dns_1: str | None = None,
    dhcp_dns_2: str | None = None,
    dhcp_dns_3: str | None = None,
    dhcp_dns_4: str | None = None,
    domain_name: str | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update an existing network.

    Uses the official Integration API: PUT /v1/sites/{id}/networks/{networkId}

    Args:
        site_id: Site identifier
        network_id: Network ID
        settings: Application settings
        name: New network name
        vlan_id: New VLAN ID (1-4094)
        subnet: New subnet in CIDR notation
        purpose: New purpose (corporate, guest, vlan-only)
        dhcp_enabled: Enable/disable DHCP
        dhcp_start: New DHCP range start IP
        dhcp_stop: New DHCP range stop IP
        dhcp_dns_1: New primary DNS server
        dhcp_dns_2: New secondary DNS server
        dhcp_dns_3: New tertiary DNS server
        dhcp_dns_4: New quaternary DNS server
        domain_name: New domain name
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't update the network

    Returns:
        Updated network dictionary or dry-run result

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If network not found
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "network configuration operation", dry_run)

    # Validate VLAN ID if provided
    if vlan_id is not None and not 1 <= vlan_id <= 4094:
        raise ValidationError(f"Invalid VLAN ID {vlan_id}. Must be between 1 and 4094")

    # Validate purpose if provided
    if purpose is not None:
        valid_purposes = ["corporate", "guest", "vlan-only", "wan"]
        if purpose not in valid_purposes:
            raise ValidationError(f"Invalid purpose '{purpose}'. Must be one of: {valid_purposes}")

    # Validate subnet format if provided
    if subnet is not None and "/" not in subnet:
        raise ValidationError(f"Invalid subnet '{subnet}'. Must be in CIDR notation")

    parameters = {
        "site_id": site_id,
        "network_id": network_id,
        "name": name,
        "vlan_id": vlan_id,
        "subnet": subnet,
        "purpose": purpose,
        "dhcp_enabled": dhcp_enabled,
    }

    if dry_run:
        logger.info(f"DRY RUN: Would update network '{network_id}' in site '{site_id}'")
        await log_audit(
            operation="update_network",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_update": parameters}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)

        # Fetch existing network by ID
        try:
            existing = await client.get(
                client.integration_path(site.uuid, f"networks/{network_id}")
            )
        except Exception as e:
            if "404" in str(e) or "not found" in str(e).lower():
                raise ResourceNotFoundError("network", network_id) from e
            raise

        if not existing or not isinstance(existing, dict):
            raise ResourceNotFoundError("network", network_id)

        update_data = _build_network_payload(
            name=name,
            vlan_id=vlan_id,
            subnet=subnet,
            purpose=purpose,
            dhcp_enabled=dhcp_enabled,
            dhcp_start=dhcp_start,
            dhcp_stop=dhcp_stop,
            dhcp_dns_1=dhcp_dns_1,
            dhcp_dns_2=dhcp_dns_2,
            dhcp_dns_3=dhcp_dns_3,
            dhcp_dns_4=dhcp_dns_4,
            domain_name=domain_name,
        )

        response = await client.put(
            client.integration_path(site.uuid, f"networks/{network_id}"),
            json_data=update_data,
        )
        updated_network = response if isinstance(response, dict) else {}

        logger.info(f"Updated network '{network_id}' in site '{site_id}'")
        await log_audit(
            operation="update_network",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return updated_network

    except Exception as e:
        logger.error(f"Failed to update network '{network_id}': {e}")
        await log_audit(
            operation="update_network",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def delete_network(
    site_id: str,
    network_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Delete a network.

    Uses the official Integration API: DELETE /v1/sites/{id}/networks/{networkId}

    Args:
        site_id: Site identifier
        network_id: Network ID
        settings: Application settings
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't delete the network

    Returns:
        Deletion result dictionary

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If network not found
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "network configuration operation", dry_run)

    parameters = {"site_id": site_id, "network_id": network_id}

    if dry_run:
        logger.info(f"DRY RUN: Would delete network '{network_id}' from site '{site_id}'")
        await log_audit(
            operation="delete_network",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_delete": network_id}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)

        try:
            existing = await client.get(
                client.integration_path(site.uuid, f"networks/{network_id}")
            )
        except Exception as e:
            if "404" in str(e) or "not found" in str(e).lower():
                raise ResourceNotFoundError("network", network_id) from e
            raise

        if not existing or not isinstance(existing, dict):
            raise ResourceNotFoundError("network", network_id)

        await client.delete(client.integration_path(site.uuid, f"networks/{network_id}"))

        logger.info(f"Deleted network '{network_id}' from site '{site_id}'")
        await log_audit(
            operation="delete_network",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return {"success": True, "deleted_network_id": network_id}

    except Exception as e:
        logger.error(f"Failed to delete network '{network_id}': {e}")
        await log_audit(
            operation="delete_network",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise

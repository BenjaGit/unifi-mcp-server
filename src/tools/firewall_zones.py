"""Firewall zone management tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..config import APIType, Settings
from ..models.zbf_matrix import ZoneNetworkAssignment
from ..utils import ValidationError, audit_action, get_logger, validate_confirmation

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = [
    "provider",
    "list_firewall_zones",
    "create_firewall_zone",
    "update_firewall_zone",
    "assign_network_to_zone",
    "get_zone_networks",
    "delete_firewall_zone",
    "unassign_network_from_zone",
]


def _ensure_local_api(settings: Settings) -> None:
    """Ensure the UniFi controller is accessed via the local API for ZBF operations."""
    if settings.api_type != APIType.LOCAL:
        raise ValidationError(
            "Zone-Based Firewall endpoints are only available when UNIFI_API_TYPE='local'. "
            "Please configure a local UniFi gateway connection to use these tools."
        )


@provider.tool()
async def list_firewall_zones(site_id: str) -> list[dict[str, Any]]:
    """List all firewall zones for a site.

    Args:
        site_id: Site identifier
        settings: Application settings

    Returns:
        List of firewall zones
    """
    client = get_network_client()
    _ensure_local_api(client.settings)

    logger.info(f"Listing firewall zones for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    endpoint = client.integration_path(site.uuid, "firewall/zones")
    response = await client.get(endpoint)
    data = response if isinstance(response, list) else response.get("data", [])
    return data if isinstance(data, list) else []


@provider.tool(annotations={"destructiveHint": True})
async def create_firewall_zone(
    site_id: str,
    name: str,
    description: str | None = None,
    network_ids: list[str] | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create a new firewall zone.

    Args:
        site_id: Site identifier
        name: Zone name
        settings: Application settings
        description: Zone description
        network_ids: Network IDs to assign to this zone
        confirm: Confirmation flag (required)
        dry_run: If True, validate but don't execute

    Returns:
        Created firewall zone
    """
    validate_confirmation(confirm, "create firewall zone", dry_run)

    client = get_network_client()
    _ensure_local_api(client.settings)

    logger.info(f"Creating firewall zone '{name}' for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    payload: dict[str, Any] = {
        "name": name,
        "networkIds": network_ids if network_ids else [],
    }

    if description:
        payload["description"] = description

    if dry_run:
        logger.info(f"[DRY RUN] Would create firewall zone with payload: {payload}")
        return {"dry_run": True, "payload": payload}

    site = await client.resolve_site(site_id)
    response = await client.post(
        client.integration_path(site.uuid, "firewall/zones"),
        json_data=payload,
    )
    data = response.get("data", response)

    await audit_action(
        client.settings,
        action_type="create_firewall_zone",
        resource_type="firewall_zone",
        resource_id=data.get("_id", "unknown"),
        site_id=site_id,
        details={"name": name},
    )

    return data if isinstance(data, dict) else {}


@provider.tool(annotations={"destructiveHint": True})
async def update_firewall_zone(
    site_id: str,
    firewall_zone_id: str,
    name: str | None = None,
    description: str | None = None,
    network_ids: list[str] | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update an existing firewall zone.

    Args:
        site_id: Site identifier
        firewall_zone_id: Firewall zone identifier
        settings: Application settings
        name: Zone name
        description: Zone description
        network_ids: Network IDs to assign to this zone
        confirm: Confirmation flag (required)
        dry_run: If True, validate but don't execute

    Returns:
        Updated firewall zone
    """
    validate_confirmation(confirm, "update firewall zone", dry_run)

    client = get_network_client()
    _ensure_local_api(client.settings)

    logger.info(f"Updating firewall zone {firewall_zone_id} for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    current_zone_response = await client.get(
        client.integration_path(site.uuid, f"firewall/zones/{firewall_zone_id}")
    )
    current_zone = current_zone_response.get("data", current_zone_response)
    current_network_ids = current_zone.get("networkIds", [])

    payload: dict[str, Any] = {
        "networkIds": network_ids if network_ids is not None else current_network_ids
    }

    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description

    if dry_run:
        logger.info(f"[DRY RUN] Would update firewall zone with payload: {payload}")
        return {"dry_run": True, "payload": payload}

    response = await client.put(
        client.integration_path(site.uuid, f"firewall/zones/{firewall_zone_id}"),
        json_data=payload,
    )
    data = response.get("data", response)

    await audit_action(
        client.settings,
        action_type="update_firewall_zone",
        resource_type="firewall_zone",
        resource_id=firewall_zone_id,
        site_id=site_id,
        details=payload,
    )

    return data if isinstance(data, dict) else {}


@provider.tool(annotations={"destructiveHint": True})
async def assign_network_to_zone(
    site_id: str,
    zone_id: str,
    network_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Dynamically assign a network to a zone.

    Args:
        site_id: Site identifier
        zone_id: Zone identifier
        network_id: Network identifier to assign
        settings: Application settings
        confirm: Confirmation flag (required)
        dry_run: If True, validate but don't execute

    Returns:
        Network assignment information
    """
    validate_confirmation(confirm, "assign network to zone", dry_run)

    client = get_network_client()
    _ensure_local_api(client.settings)

    logger.info(f"Assigning network {network_id} to zone {zone_id} on site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    network_name = None
    try:
        network_response = await client.get(
            client.integration_path(site.uuid, f"networks/{network_id}")
        )
        network_data = network_response.get("data", {})
        network_name = network_data.get("name")
    except Exception:  # pragma: no cover - best-effort logging
        logger.warning(f"Could not fetch network name for {network_id}")

    zone_response = await client.get(
        client.integration_path(site.uuid, f"firewall/zones/{zone_id}")
    )
    zone_data = zone_response.get("data", {})
    current_networks = zone_data.get("networks", [])

    if network_id in current_networks:
        logger.info(f"Network {network_id} already assigned to zone {zone_id}")
        return ZoneNetworkAssignment(
            zone_id=zone_id,
            network_id=network_id,
            network_name=network_name,
            assigned_at=None,
        ).model_dump()

    updated_networks = list(current_networks) + [network_id]
    payload = {"networks": updated_networks}

    if dry_run:
        logger.info(f"[DRY RUN] Would assign network {network_id} to zone {zone_id}")
        return {"dry_run": True, "payload": payload}

    await client.put(
        client.integration_path(site.uuid, f"firewall/zones/{zone_id}"),
        json_data=payload,
    )

    await audit_action(
        client.settings,
        action_type="assign_network_to_zone",
        resource_type="zone_network_assignment",
        resource_id=network_id,
        site_id=site_id,
        details={"zone_id": zone_id, "network_id": network_id},
    )

    return ZoneNetworkAssignment(
        zone_id=zone_id,
        network_id=network_id,
        network_name=network_name,
        assigned_at=None,
    ).model_dump()


@provider.tool()
async def get_zone_networks(site_id: str, zone_id: str) -> list[dict[str, Any]]:
    """List all networks in a zone.

    Args:
        site_id: Site identifier
        zone_id: Zone identifier
        settings: Application settings

    Returns:
        List of networks in the zone
    """
    client = get_network_client()
    _ensure_local_api(client.settings)

    logger.info(f"Listing networks in zone {zone_id} on site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    response = await client.get(client.integration_path(site.uuid, "firewall/zones"))
    zones_data = response if isinstance(response, list) else response.get("data", [])
    zone_data: dict[str, Any] = next((z for z in zones_data if z.get("id") == zone_id), {})
    network_ids = zone_data.get("networkIds", zone_data.get("networks", []))

    networks = []
    for network_id in network_ids:
        try:
            network_response = await client.get(
                client.integration_path(site.uuid, f"networks/{network_id}")
            )
            network_data = network_response.get("data", {})
            networks.append(
                ZoneNetworkAssignment(
                    zone_id=zone_id,
                    network_id=network_id,
                    network_name=network_data.get("name"),
                    assigned_at=None,
                ).model_dump()
            )
        except Exception:  # pragma: no cover - best-effort fetch
            networks.append(
                ZoneNetworkAssignment(
                    zone_id=zone_id,
                    network_id=network_id,
                    network_name=None,
                    assigned_at=None,
                ).model_dump()
            )

    return networks


@provider.tool(annotations={"destructiveHint": True})
async def delete_firewall_zone(
    site_id: str,
    zone_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Delete a firewall zone.

    Args:
        site_id: Site identifier
        zone_id: Zone identifier to delete
        settings: Application settings
        confirm: Confirmation flag (required)
        dry_run: If True, validate but don't execute

    Returns:
        Deletion confirmation

    Raises:
        ValueError: If confirmation not provided
    """
    validate_confirmation(confirm, "delete firewall zone", dry_run)

    client = get_network_client()
    _ensure_local_api(client.settings)

    logger.info(f"Deleting firewall zone {zone_id} from site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    if dry_run:
        logger.info(f"[DRY RUN] Would delete firewall zone {zone_id}")
        return {"dry_run": True, "zone_id": zone_id, "action": "would_delete"}

    site = await client.resolve_site(site_id)
    await client.delete(client.integration_path(site.uuid, f"firewall/zones/{zone_id}"))

    await audit_action(
        client.settings,
        action_type="delete_firewall_zone",
        resource_type="firewall_zone",
        resource_id=zone_id,
        site_id=site_id,
        details={"zone_id": zone_id},
    )

    return {"status": "success", "zone_id": zone_id, "action": "deleted"}


@provider.tool(annotations={"destructiveHint": True})
async def unassign_network_from_zone(
    site_id: str,
    zone_id: str,
    network_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Remove a network from a firewall zone.

    Args:
        site_id: Site identifier
        zone_id: Zone identifier
        network_id: Network identifier to remove
        settings: Application settings
        confirm: Confirmation flag (required)
        dry_run: If True, validate but don't execute

    Returns:
        Network unassignment confirmation

    Raises:
        ValueError: If confirmation not provided or network not in zone
    """
    validate_confirmation(confirm, "unassign network from zone", dry_run)

    client = get_network_client()
    _ensure_local_api(client.settings)

    logger.info(f"Unassigning network {network_id} from zone {zone_id} on site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    zone_response = await client.get(
        client.integration_path(site.uuid, f"firewall/zones/{zone_id}")
    )
    zone_data = zone_response.get("data", {})
    current_networks = zone_data.get("networks", [])

    if network_id not in current_networks:
        raise ValueError(f"Network {network_id} is not assigned to zone {zone_id}")

    updated_networks = [nid for nid in current_networks if nid != network_id]

    payload = {"networks": updated_networks}

    if dry_run:
        logger.info(f"[DRY RUN] Would remove network {network_id} from zone {zone_id}")
        return {"dry_run": True, "payload": payload}

    await client.put(
        client.integration_path(site.uuid, f"firewall/zones/{zone_id}"),
        json_data=payload,
    )

    await audit_action(
        client.settings,
        action_type="unassign_network_from_zone",
        resource_type="zone_network_assignment",
        resource_id=network_id,
        site_id=site_id,
        details={"zone_id": zone_id, "network_id": network_id},
    )

    return {
        "status": "success",
        "zone_id": zone_id,
        "network_id": network_id,
        "action": "unassigned",
    }


async def get_zone_statistics(
    site_id: str,
    zone_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """Get traffic statistics for a firewall zone.

    ⚠️ **DEPRECATED - ENDPOINT DOES NOT EXIST**

    This endpoint has been verified to NOT EXIST in UniFi Network API v10.0.156.
    Tested on UniFi Express 7 and UDM Pro on 2025-11-18.

    Zone traffic statistics are not available via the API.
    Monitor traffic via /sites/{siteId}/clients endpoint instead.

    See tests/verification/PHASE2_FINDINGS.md for details.

    Args:
        site_id: Site identifier
        zone_id: Zone identifier
        settings: Application settings

    Returns:
        Zone traffic statistics including bandwidth usage and connection counts

    Raises:
        NotImplementedError: This endpoint does not exist in the UniFi API
    """
    logger.warning(
        f"get_zone_statistics called for zone {zone_id} but endpoint does not exist in UniFi API v10.0.156."
    )
    raise NotImplementedError(
        "Zone statistics endpoint does not exist in UniFi Network API v10.0.156. "
        "Verified on U7 Express and UDM Pro (2025-11-18). "
        "Monitor traffic via /sites/{siteId}/clients endpoint instead. "
        "See tests/verification/PHASE2_FINDINGS.md for details."
    )

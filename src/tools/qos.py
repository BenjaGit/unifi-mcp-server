"""Traffic route management tools.

Note: QoS Profile Management (5 tools), ProAV Profile Management (3 tools),
and Smart Queue Management (3 tools) were removed because they used endpoints
(rest/qosprofile, rest/wanconf) that do not exist on any UniFi API surface
(local gateway or cloud EA). These tools were AI-generated against assumed
endpoint patterns that Ubiquiti never implemented. The unit tests passed
because they mock the HTTP layer, so the non-existent endpoints were never
caught until tested against real hardware.

See: https://developer.ui.com/network/ for documented endpoints.
"""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..models.qos_profile import TrafficRoute
from ..utils import (
    ValidationError,
    audit_action,
    get_logger,
    validate_confirmation,
    validate_site_id,
)

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = [
    "provider",
    "list_traffic_routes",
    "create_traffic_route",
    "update_traffic_route",
    "delete_traffic_route",
]


@provider.tool()
async def list_traffic_routes(
    site_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List all traffic routing policies for a site."""
    site_id = validate_site_id(site_id)
    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "rest/routing"))
    data = response if isinstance(response, list) else response.get("data", [])
    paginated_data = data[offset : offset + limit]
    logger.info(f"Listing traffic routes for site {site_id} (limit={limit}, offset={offset})")
    return [TrafficRoute(**route).model_dump() for route in paginated_data]


@provider.tool()
async def create_traffic_route(
    site_id: str,
    name: str,
    action: str,
    description: str | None = None,
    source_ip: str | None = None,
    destination_ip: str | None = None,
    source_port: int | None = None,
    destination_port: int | None = None,
    protocol: str | None = None,
    vlan_id: int | None = None,
    dscp_marking: int | None = None,
    bandwidth_limit_kbps: int | None = None,
    priority: int = 100,
    enabled: bool = True,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create a new traffic routing policy."""
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "create traffic route", dry_run)

    valid_actions = ["allow", "deny", "mark", "shape"]
    if action not in valid_actions:
        raise ValidationError(f"Invalid action '{action}'. Use: {', '.join(valid_actions)}")
    if dscp_marking is not None and not 0 <= dscp_marking <= 63:
        raise ValidationError(f"DSCP marking must be 0-63, got {dscp_marking}")
    if not 1 <= priority <= 1000:
        raise ValidationError(f"Priority must be 1-1000, got {priority}")

    match_criteria: dict[str, Any] = {}
    if source_ip:
        match_criteria["source_ip"] = source_ip
    if destination_ip:
        match_criteria["destination_ip"] = destination_ip
    if source_port:
        match_criteria["source_port"] = source_port
    if destination_port:
        match_criteria["destination_port"] = destination_port
    if protocol:
        match_criteria["protocol"] = protocol
    if vlan_id:
        match_criteria["vlan_id"] = vlan_id

    route_data: dict[str, Any] = {
        "name": name,
        "action": action,
        "match_criteria": match_criteria,
        "priority": priority,
        "enabled": enabled,
    }
    if description:
        route_data["description"] = description
    if dscp_marking is not None:
        route_data["dscp_marking"] = dscp_marking
    if bandwidth_limit_kbps is not None:
        route_data["bandwidth_limit_kbps"] = bandwidth_limit_kbps

    if dry_run:
        logger.info(f"[DRY RUN] Would create traffic route: {route_data}")
        return {"dry_run": True, "route": route_data}

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.post(
        client.legacy_path(site.name, "rest/routing"), json_data=route_data
    )
    data = response if isinstance(response, list) else response.get("data", [])
    if not data:
        raise ValidationError("Failed to create traffic route")

    result = TrafficRoute(**data[0]).model_dump()
    await audit_action(
        getattr(client, "settings", None),
        action_type="create_traffic_route",
        resource_type="traffic_route",
        resource_id=result.get("id", "unknown"),
        details={"name": name, "action": action},
        site_id=site_id,
    )
    return result


@provider.tool()
async def update_traffic_route(
    site_id: str,
    route_id: str,
    name: str | None = None,
    action: str | None = None,
    description: str | None = None,
    enabled: bool | None = None,
    priority: int | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update an existing traffic routing policy."""
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "update traffic route", dry_run)

    update_data: dict[str, Any] = {}
    if name is not None:
        update_data["name"] = name
    if action is not None:
        update_data["action"] = action
    if description is not None:
        update_data["description"] = description
    if enabled is not None:
        update_data["enabled"] = enabled
    if priority is not None:
        if not 1 <= priority <= 1000:
            raise ValidationError(f"Priority must be 1-1000, got {priority}")
        update_data["priority"] = priority
    if not update_data:
        raise ValidationError("No update fields provided")

    if dry_run:
        logger.info(f"[DRY RUN] Would update traffic route {route_id}: {update_data}")
        return {"dry_run": True, "route_id": route_id, "updates": update_data}

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.put(
        client.legacy_path(site.name, f"rest/routing/{route_id}"), json_data=update_data
    )
    data = response if isinstance(response, list) else response.get("data", [])
    if not data:
        raise ValidationError(f"Failed to update traffic route {route_id}")

    result = TrafficRoute(**data[0]).model_dump()
    await audit_action(
        getattr(client, "settings", None),
        action_type="update_traffic_route",
        resource_type="traffic_route",
        resource_id=route_id,
        details=update_data,
        site_id=site_id,
    )
    return result


@provider.tool(annotations={"destructiveHint": True})
async def delete_traffic_route(
    site_id: str,
    route_id: str,
    confirm: bool | str = False,
) -> dict[str, Any]:
    """Delete a traffic routing policy."""
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "delete traffic route")

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    await client.delete(client.legacy_path(site.name, f"rest/routing/{route_id}"))

    await audit_action(
        getattr(client, "settings", None),
        action_type="delete_traffic_route",
        resource_type="traffic_route",
        resource_id=route_id,
        details={"deleted": True},
        site_id=site_id,
    )
    return {
        "success": True,
        "message": f"Traffic route {route_id} deleted successfully",
        "route_id": route_id,
    }

"""Access Control List (ACL) management tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..models import ACLRule
from ..utils import audit_action, get_logger, validate_confirmation

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = [
    "provider",
    "list_acl_rules",
    "get_acl_rule",
    "create_acl_rule",
    "update_acl_rule",
    "delete_acl_rule",
    "get_acl_rule_ordering",
    "update_acl_rule_ordering",
]


@provider.tool()
async def list_acl_rules(
    site_id: str,
    limit: int | None = None,
    offset: int | None = None,
    filter_expr: str | None = None,
) -> list[dict[str, Any]]:
    """List all ACL rules for a site."""
    client = get_network_client()
    logger.info(f"Listing ACL rules for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    params: dict[str, Any] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    if filter_expr:
        params["filter"] = filter_expr

    response = await client.get(client.integration_path(site.uuid, "acl-rules"), params=params)
    data = response if isinstance(response, list) else response.get("data", [])
    return [ACLRule(**rule).model_dump() for rule in data]


@provider.tool()
async def get_acl_rule(site_id: str, acl_rule_id: str) -> dict[str, Any]:
    """Get details for a specific ACL rule."""
    client = get_network_client()
    logger.info(f"Getting ACL rule {acl_rule_id} for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.integration_path(site.uuid, f"acl-rules/{acl_rule_id}"))
    data = response.get("data", response) if isinstance(response, dict) else response
    return ACLRule(**data).model_dump()


@provider.tool()
async def create_acl_rule(
    site_id: str,
    name: str,
    action: str,
    enabled: bool = True,
    source_type: str | None = None,
    source_id: str | None = None,
    source_network: str | None = None,
    destination_type: str | None = None,
    destination_id: str | None = None,
    destination_network: str | None = None,
    protocol: str | None = None,
    src_port: int | None = None,
    dst_port: int | None = None,
    priority: int = 100,
    description: str | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create a new ACL rule."""
    validate_confirmation(confirm, "create ACL rule", dry_run)
    client = get_network_client()
    logger.info(f"Creating ACL rule '{name}' for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    payload: dict[str, Any] = {
        "name": name,
        "enabled": enabled,
        "action": action,
        "priority": priority,
    }
    if description:
        payload["description"] = description
    if source_type:
        payload["sourceType"] = source_type
    if source_id:
        payload["sourceId"] = source_id
    if source_network:
        payload["sourceNetwork"] = source_network
    if destination_type:
        payload["destinationType"] = destination_type
    if destination_id:
        payload["destinationId"] = destination_id
    if destination_network:
        payload["destinationNetwork"] = destination_network
    if protocol:
        payload["protocol"] = protocol
    if src_port is not None:
        payload["srcPort"] = src_port
    if dst_port is not None:
        payload["dstPort"] = dst_port

    if dry_run:
        logger.info(f"[DRY RUN] Would create ACL rule with payload: {payload}")
        return {"dry_run": True, "payload": payload}

    response = await client.post(client.integration_path(site.uuid, "acl-rules"), json_data=payload)
    data = response.get("data", response) if isinstance(response, dict) else response

    await audit_action(
        client.settings,
        action_type="create_acl_rule",
        resource_type="acl_rule",
        resource_id=data.get("_id", "unknown"),
        site_id=site_id,
        details={"name": name, "action": action},
    )
    return ACLRule(**data).model_dump()


@provider.tool()
async def update_acl_rule(
    site_id: str,
    acl_rule_id: str,
    name: str | None = None,
    action: str | None = None,
    enabled: bool | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
    source_network: str | None = None,
    destination_type: str | None = None,
    destination_id: str | None = None,
    destination_network: str | None = None,
    protocol: str | None = None,
    src_port: int | None = None,
    dst_port: int | None = None,
    priority: int | None = None,
    description: str | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update an existing ACL rule."""
    validate_confirmation(confirm, "update ACL rule", dry_run)
    client = get_network_client()
    logger.info(f"Updating ACL rule {acl_rule_id} for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    payload: dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if action is not None:
        payload["action"] = action
    if enabled is not None:
        payload["enabled"] = enabled
    if priority is not None:
        payload["priority"] = priority
    if description is not None:
        payload["description"] = description
    if source_type is not None:
        payload["sourceType"] = source_type
    if source_id is not None:
        payload["sourceId"] = source_id
    if source_network is not None:
        payload["sourceNetwork"] = source_network
    if destination_type is not None:
        payload["destinationType"] = destination_type
    if destination_id is not None:
        payload["destinationId"] = destination_id
    if destination_network is not None:
        payload["destinationNetwork"] = destination_network
    if protocol is not None:
        payload["protocol"] = protocol
    if src_port is not None:
        payload["srcPort"] = src_port
    if dst_port is not None:
        payload["dstPort"] = dst_port

    if dry_run:
        logger.info(f"[DRY RUN] Would update ACL rule with payload: {payload}")
        return {"dry_run": True, "payload": payload}

    response = await client.put(
        client.integration_path(site.uuid, f"acl-rules/{acl_rule_id}"), json_data=payload
    )
    data = response.get("data", response) if isinstance(response, dict) else response

    await audit_action(
        client.settings,
        action_type="update_acl_rule",
        resource_type="acl_rule",
        resource_id=acl_rule_id,
        site_id=site_id,
        details=payload,
    )
    return ACLRule(**data).model_dump()


@provider.tool(annotations={"destructiveHint": True})
async def delete_acl_rule(
    site_id: str,
    acl_rule_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Delete an ACL rule."""
    validate_confirmation(confirm, "delete ACL rule", dry_run)
    client = get_network_client()
    logger.info(f"Deleting ACL rule {acl_rule_id} for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    if dry_run:
        logger.info(f"[DRY RUN] Would delete ACL rule {acl_rule_id}")
        return {"dry_run": True, "acl_rule_id": acl_rule_id}

    await client.delete(client.integration_path(site.uuid, f"acl-rules/{acl_rule_id}"))
    await audit_action(
        client.settings,
        action_type="delete_acl_rule",
        resource_type="acl_rule",
        resource_id=acl_rule_id,
        site_id=site_id,
        details={},
    )
    return {"success": True, "message": f"ACL rule {acl_rule_id} deleted successfully"}


@provider.tool()
async def get_acl_rule_ordering(site_id: str) -> dict[str, Any]:
    """Get ACL rule ordering for a site."""
    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.integration_path(site.uuid, "acl-rules/ordering"))
    logger.info(f"Retrieved ACL rule ordering for site {site_id}")
    return response if isinstance(response, dict) else {"orderedAclRuleIds": response}


@provider.tool()
async def update_acl_rule_ordering(
    site_id: str,
    ordered_acl_rule_ids: list[str],
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Reorder ACL rules for a site."""
    validate_confirmation(confirm, "reorder ACL rules", dry_run)
    payload = {"orderedAclRuleIds": ordered_acl_rule_ids}

    if dry_run:
        logger.info(f"[DRY RUN] Would reorder ACL rules in site {site_id}")
        return {"dry_run": True, "would_set_ordering": payload}

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.put(
        client.integration_path(site.uuid, "acl-rules/ordering"),
        json_data=payload,
    )
    await audit_action(
        client.settings,
        action_type="update_acl_rule_ordering",
        resource_type="acl_rule",
        resource_id="ordering",
        site_id=site_id,
        details={"ordered_ids": ordered_acl_rule_ids},
    )

    logger.info(f"Updated ACL rule ordering for site {site_id}")
    return response if isinstance(response, dict) else {"orderedAclRuleIds": response}

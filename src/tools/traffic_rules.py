"""Traffic rules v2 MCP tools (rate limiting by app/category)."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..config import APIType, Settings
from ..utils import get_logger, log_audit, validate_confirmation, validate_site_id
from ._helpers import resolve, unwrap

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = [
    "provider",
    "list_traffic_rules",
    "create_traffic_rule",
    "update_traffic_rule",
    "delete_traffic_rule",
]


def _ensure_local_api(settings: Settings) -> None:
    """Ensure local API — v2 traffic rules endpoint requires local gateway access."""
    if settings.api_type != APIType.LOCAL:
        raise NotImplementedError(
            "Traffic rules (v2 API) are only available when UNIFI_API_TYPE='local'. "
            "Please configure a local UniFi gateway connection to use these tools."
        )


@provider.tool()
async def list_traffic_rules(site_id: str) -> list[dict[str, Any]]:
    """List v2 traffic rules for a site.

    Traffic rules control traffic management policies (rate limiting by app/category).
    These are distinct from the legacy QoS routes in rest/routing.

    Only available with local gateway API (api_type="local").

    Args:
        site_id: Site identifier
        settings: Application settings

    Returns:
        List of traffic rule objects
    """
    site_id = validate_site_id(site_id)
    client = get_network_client()
    _ensure_local_api(client.settings)

    client, site = await resolve(site_id, get_network_client)
    response = await client.get(client.v2_path(site.name, "trafficrules"))

    data: list[dict[str, Any]] = unwrap(response)
    logger.info(f"Listed {len(data)} traffic rules for site '{site_id}'")
    return data


@provider.tool(annotations={"destructiveHint": True})
async def create_traffic_rule(
    site_id: str,
    rule_data: dict[str, Any],
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create a v2 traffic rule.

    Only available with local gateway API (api_type="local").

    Args:
        site_id: Site identifier
        rule_data: Traffic rule configuration dict (passed as-is to the API)
        settings: Application settings
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't create

    Returns:
        Created traffic rule object
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "create traffic rule", dry_run)
    client = get_network_client()
    _ensure_local_api(client.settings)

    parameters = {"site_id": site_id, "rule_data": rule_data}

    if dry_run:
        logger.info(f"DRY RUN: Would create traffic rule in site '{site_id}'")
        await log_audit(
            operation="create_traffic_rule",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_create": rule_data}

    try:
        _, site = await resolve(site_id, get_network_client)
        result = await client.post(client.v2_path(site.name, "trafficrules"), json_data=rule_data)
        await log_audit(
            operation="create_traffic_rule",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )
        return result if isinstance(result, dict) else {"data": result}
    except Exception as e:
        logger.error(f"Failed to create traffic rule: {e}")
        await log_audit(
            operation="create_traffic_rule", parameters=parameters, result="failed", site_id=site_id
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def update_traffic_rule(
    site_id: str,
    rule_id: str,
    rule_data: dict[str, Any],
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update a v2 traffic rule.

    Only available with local gateway API (api_type="local").

    Args:
        site_id: Site identifier
        rule_id: Traffic rule ID
        rule_data: Updated traffic rule configuration (full object)
        settings: Application settings
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't update

    Returns:
        Updated traffic rule object
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "update traffic rule", dry_run)
    client = get_network_client()
    _ensure_local_api(client.settings)

    parameters = {"site_id": site_id, "rule_id": rule_id}

    if dry_run:
        logger.info(f"DRY RUN: Would update traffic rule '{rule_id}' in site '{site_id}'")
        await log_audit(
            operation="update_traffic_rule",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_update": rule_id}

    try:
        _, site = await resolve(site_id, get_network_client)
        result = await client.put(
            client.v2_path(site.name, f"trafficrules/{rule_id}"),
            json_data=rule_data,
        )
        await log_audit(
            operation="update_traffic_rule",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )
        return result if isinstance(result, dict) else {"data": result}
    except Exception as e:
        logger.error(f"Failed to update traffic rule '{rule_id}': {e}")
        await log_audit(
            operation="update_traffic_rule", parameters=parameters, result="failed", site_id=site_id
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def delete_traffic_rule(
    site_id: str,
    rule_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Delete a v2 traffic rule.

    Only available with local gateway API (api_type="local").

    Args:
        site_id: Site identifier
        rule_id: Traffic rule ID
        settings: Application settings
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't delete

    Returns:
        Deletion result dictionary
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "delete traffic rule", dry_run)
    client = get_network_client()
    _ensure_local_api(client.settings)

    parameters = {"site_id": site_id, "rule_id": rule_id}

    if dry_run:
        logger.info(f"DRY RUN: Would delete traffic rule '{rule_id}' from site '{site_id}'")
        await log_audit(
            operation="delete_traffic_rule",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_delete": rule_id}

    try:
        _, site = await resolve(site_id, get_network_client)
        await client.delete(client.v2_path(site.name, f"trafficrules/{rule_id}"))
        await log_audit(
            operation="delete_traffic_rule",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )
        return {"success": True, "rule_id": rule_id}
    except Exception as e:
        logger.error(f"Failed to delete traffic rule '{rule_id}': {e}")
        await log_audit(
            operation="delete_traffic_rule", parameters=parameters, result="failed", site_id=site_id
        )
        raise

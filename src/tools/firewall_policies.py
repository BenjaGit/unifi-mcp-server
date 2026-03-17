"""Firewall policies management tools for UniFi v2 API."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..config import APIType, Settings
from ..models.firewall_policy import FirewallPolicy, FirewallPolicyCreate
from ..utils import ResourceNotFoundError, get_logger, log_audit
from ..utils.validators import coerce_bool

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = [
    "provider",
    "list_firewall_policies",
    "get_firewall_policy",
    "create_firewall_policy",
    "update_firewall_policy",
    "delete_firewall_policy",
    "get_firewall_policy_ordering",
    "update_firewall_policy_ordering",
]


def _ensure_local_api(settings: Settings) -> None:
    """Ensure the UniFi controller is accessed via the local API for v2 endpoints."""

    if settings.api_type != APIType.LOCAL:
        raise NotImplementedError(
            "Firewall policies (v2 API) are only available when UNIFI_API_TYPE='local'. "
            "Please configure a local UniFi gateway connection to use these tools."
        )


@provider.tool()
async def list_firewall_policies(site_id: str) -> list[dict[str, Any]]:
    """List all firewall policies (Traffic & Firewall Rules) for a site."""

    client = get_network_client()
    _ensure_local_api(client.settings)

    logger.info(f"Listing firewall policies for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    endpoint = client.v2_path(site.name, "firewall-policies")
    response = await client.get(endpoint)

    policies_data = response if isinstance(response, list) else response.get("data", [])
    return [FirewallPolicy(**policy).model_dump() for policy in policies_data]


@provider.tool()
async def get_firewall_policy(policy_id: str, site_id: str) -> dict[str, Any]:
    """Get a specific firewall policy by ID."""

    client = get_network_client()
    _ensure_local_api(client.settings)

    logger.info(f"Getting firewall policy {policy_id} for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    endpoint = client.v2_path(site.name, f"firewall-policies/{policy_id}")

    try:
        response = await client.get(endpoint)
    except ResourceNotFoundError as err:
        raise ResourceNotFoundError("firewall_policy", policy_id) from err

    if isinstance(response, dict) and "data" in response:
        data = response["data"]
    else:
        data = response

    if not data:
        raise ResourceNotFoundError("firewall_policy", policy_id)

    return FirewallPolicy(**data).model_dump()


@provider.tool(annotations={"destructiveHint": True})
async def create_firewall_policy(
    name: str,
    action: str,
    site_id: str,
    source_zone_id: str | None = None,
    destination_zone_id: str | None = None,
    source_matching_target: str = "ANY",
    destination_matching_target: str = "ANY",
    protocol: str = "all",
    enabled: bool = True,
    description: str | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create a new firewall policy (Traffic & Firewall Rule)."""

    client = get_network_client()
    _ensure_local_api(client.settings)

    valid_actions = ["ALLOW", "BLOCK"]
    action_upper = action.upper()
    if action_upper not in valid_actions:
        raise ValueError(f"Invalid action '{action}'. Must be one of: {valid_actions}")

    source_config: dict[str, Any] = {"matching_target": source_matching_target.upper()}
    if source_zone_id:
        source_config["zone_id"] = source_zone_id

    destination_config: dict[str, Any] = {"matching_target": destination_matching_target.upper()}
    if destination_zone_id:
        destination_config["zone_id"] = destination_zone_id

    policy_data = FirewallPolicyCreate(
        name=name,
        action=action_upper,
        enabled=enabled,
        protocol=protocol,
        ip_version="BOTH",
        connection_state_type="ALL",
        connection_states=None,
        source=source_config,
        destination=destination_config,
        description=description,
        index=None,
        schedule=None,
    )

    parameters = {
        "site_id": site_id,
        "name": name,
        "action": action_upper,
        "enabled": enabled,
    }

    if dry_run:
        logger.info(f"DRY RUN: Would create firewall policy '{name}' in site '{site_id}'")
        await log_audit(
            operation="create_firewall_policy",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {
            "status": "dry_run",
            "message": f"Would create firewall policy '{name}'",
            "policy": policy_data.model_dump(exclude_none=True),
        }

    if not confirm:
        raise ValueError(
            "This operation requires confirm=True to execute. "
            "Use dry_run=True to preview changes first."
        )

    try:
        logger.info(f"Creating firewall policy '{name}' for site {site_id}")

        if not client.is_authenticated:
            await client.authenticate()

        site = await client.resolve_site(site_id)

        endpoint = client.v2_path(site.name, "firewall-policies")
        response = await client.post(endpoint, json_data=policy_data.model_dump(exclude_none=True))

        if isinstance(response, dict) and "data" in response:
            data = response["data"]
        else:
            data = response

        logger.info(f"Created firewall policy '{name}' in site '{site_id}'")
        await log_audit(
            operation="create_firewall_policy",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return FirewallPolicy(**data).model_dump()

    except Exception as exc:  # pragma: no cover - logged and re-raised
        logger.error(f"Failed to create firewall policy '{name}': {exc}")
        await log_audit(
            operation="create_firewall_policy",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def update_firewall_policy(
    policy_id: str,
    site_id: str = "default",
    name: str | None = None,
    action: str | None = None,
    enabled: bool | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update an existing firewall policy."""

    client = get_network_client()
    _ensure_local_api(client.settings)

    dry_run_flag = coerce_bool(dry_run)
    confirm_flag = coerce_bool(confirm)

    if not dry_run_flag and not confirm_flag:
        raise ValueError(
            "This operation requires confirm=True to execute. "
            "Use dry_run=True to preview changes first."
        )

    update_data: dict[str, Any] = {}
    if name is not None:
        update_data["name"] = name
    if action is not None:
        action_upper = action.upper()
        if action_upper not in ["ALLOW", "BLOCK"]:
            raise ValueError(f"Invalid action '{action}'. Must be ALLOW or BLOCK.")
        update_data["action"] = action_upper
    if enabled is not None:
        update_data["enabled"] = enabled

    if dry_run_flag:
        logger.info(f"DRY RUN: Would update firewall policy {policy_id}")
        return {
            "status": "dry_run",
            "policy_id": policy_id,
            "changes": update_data,
        }

    logger.info(f"Updating firewall policy {policy_id} for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    endpoint = client.v2_path(site.name, f"firewall-policies/{policy_id}")

    try:
        response = await client.put(endpoint, json_data=update_data)
    except ResourceNotFoundError as err:
        raise ResourceNotFoundError("firewall_policy", policy_id) from err

    if isinstance(response, dict) and "data" in response:
        data = response["data"]
    else:
        data = response

    logger.info(f"Updated firewall policy {policy_id}")
    await log_audit(
        operation="update_firewall_policy",
        parameters={"policy_id": policy_id, "site_id": site_id, **update_data},
        result="success",
        site_id=site_id,
    )

    return FirewallPolicy(**data).model_dump()


@provider.tool(annotations={"destructiveHint": True})
async def delete_firewall_policy(
    policy_id: str,
    site_id: str = "default",
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Delete a firewall policy."""

    client = get_network_client()
    _ensure_local_api(client.settings)

    dry_run_flag = coerce_bool(dry_run)
    confirm_flag = coerce_bool(confirm)

    if not dry_run_flag and not confirm_flag:
        raise ValueError("This operation deletes a firewall policy. Pass confirm=True to proceed.")

    logger.info(f"Deleting firewall policy {policy_id} from site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    endpoint = client.v2_path(site.name, f"firewall-policies/{policy_id}")

    try:
        policy_response = await client.get(endpoint)
    except ResourceNotFoundError as err:
        raise ResourceNotFoundError("firewall_policy", policy_id) from err

    if isinstance(policy_response, dict) and "data" in policy_response:
        policy_data = policy_response["data"]
    else:
        policy_data = policy_response

    if not policy_data:
        raise ResourceNotFoundError("firewall_policy", policy_id)

    policy = FirewallPolicy(**policy_data)

    if policy.predefined:
        raise ValueError(
            f"Cannot delete predefined system rule '{policy.name}' (id={policy_id}). "
            "Predefined rules are managed by the UniFi system."
        )

    if dry_run_flag:
        logger.info(f"DRY RUN: Would delete firewall policy {policy_id}")
        return {
            "status": "dry_run",
            "policy_id": policy_id,
            "action": "would_delete",
            "policy": policy.model_dump(),
        }

    await client.delete(endpoint)

    await log_audit(
        operation="delete_firewall_policy",
        parameters={"policy_id": policy_id, "site_id": site_id},
        result="success",
        site_id=site_id,
    )

    logger.info(f"Deleted firewall policy {policy_id} from site {site_id}")

    return {
        "status": "success",
        "policy_id": policy_id,
        "action": "deleted",
    }


@provider.tool()
async def get_firewall_policy_ordering(
    site_id: str,
    source_zone_id: str,
    destination_zone_id: str,
) -> dict[str, Any]:
    """Get the ordering of firewall policies for a specific zone pair."""

    client = get_network_client()
    _ensure_local_api(client.settings)

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(
        client.integration_path(site.uuid, "firewall/policies/ordering"),
        params={
            "sourceFirewallZoneId": source_zone_id,
            "destinationFirewallZoneId": destination_zone_id,
        },
    )

    logger.info(
        f"Retrieved firewall policy ordering for zone pair "
        f"{source_zone_id} -> {destination_zone_id}"
    )
    return response if isinstance(response, dict) else {"orderedFirewallPolicyIds": response}


@provider.tool(annotations={"destructiveHint": True})
async def update_firewall_policy_ordering(
    site_id: str,
    source_zone_id: str,
    destination_zone_id: str,
    before_system_defined: list[str],
    after_system_defined: list[str],
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Reorder firewall policies for a specific zone pair."""

    client = get_network_client()
    _ensure_local_api(client.settings)

    confirm_flag = coerce_bool(confirm)
    dry_run_flag = coerce_bool(dry_run)

    if not dry_run_flag and not confirm_flag:
        from ..utils import ConfirmationRequiredError

        raise ConfirmationRequiredError("Reorder firewall policies requires confirmation")

    payload = {
        "orderedFirewallPolicyIds": {
            "beforeSystemDefined": before_system_defined,
            "afterSystemDefined": after_system_defined,
        }
    }

    parameters = {
        "site_id": site_id,
        "source_zone_id": source_zone_id,
        "destination_zone_id": destination_zone_id,
        "before_system_defined": before_system_defined,
        "after_system_defined": after_system_defined,
    }

    if dry_run_flag:
        logger.info(
            f"DRY RUN: Would reorder firewall policies for zone pair "
            f"{source_zone_id} -> {destination_zone_id}"
        )
        await log_audit(
            operation="update_firewall_policy_ordering",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
        )
        return {"dry_run": True, "would_set_ordering": payload}

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.put(
        client.integration_path(site.uuid, "firewall/policies/ordering"),
        json_data=payload,
        params={
            "sourceFirewallZoneId": source_zone_id,
            "destinationFirewallZoneId": destination_zone_id,
        },
    )

    await log_audit(
        operation="update_firewall_policy_ordering",
        parameters=parameters,
        result="success",
        site_id=site_id,
    )

    logger.info(
        f"Updated firewall policy ordering for zone pair "
        f"{source_zone_id} -> {destination_zone_id}"
    )
    return response if isinstance(response, dict) else {"orderedFirewallPolicyIds": response}

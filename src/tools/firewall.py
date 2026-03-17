"""Firewall rules management MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import (
    ResourceNotFoundError,
    get_logger,
    log_audit,
    validate_confirmation,
    validate_limit_offset,
    validate_site_id,
)

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = [
    "provider",
    "list_firewall_rules",
    "create_firewall_rule",
    "update_firewall_rule",
    "delete_firewall_rule",
    "list_firewall_groups",
    "create_firewall_group",
    "update_firewall_group",
    "delete_firewall_group",
]


@provider.tool()
async def list_firewall_rules(
    site_id: str,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    """List all firewall rules in a site (read-only).

    Args:
        site_id: Site identifier
        limit: Maximum number of rules to return
        offset: Number of rules to skip

    Returns:
        List of firewall rule dictionaries
    """
    site_id = validate_site_id(site_id)
    limit, offset = validate_limit_offset(limit, offset)

    client = get_network_client()
    site = await client.resolve_site(site_id)

    response = await client.get(client.legacy_path(site.name, "rest/firewallrule"))
    # Client now auto-unwraps the "data" field, so response is the actual data
    rules_data: list[dict[str, Any]] = (
        response if isinstance(response, list) else response.get("data", [])
    )

    # Apply pagination
    paginated = rules_data[offset : offset + limit]

    logger.info(f"Retrieved {len(paginated)} firewall rules for site '{site_id}'")
    return paginated


@provider.tool(annotations={"destructiveHint": True})
async def create_firewall_rule(
    site_id: str,
    name: str,
    action: str,
    src_address: str | None = None,
    dst_address: str | None = None,
    protocol: str | None = None,
    port: int | None = None,
    enabled: bool = True,
    ruleset: str = "WAN_IN",
    rule_index: int = 2000,
    src_networkconf_id: str | None = None,
    src_networkconf_type: str = "NETv4",
    dst_networkconf_id: str | None = None,
    dst_networkconf_type: str = "NETv4",
    state_established: bool = False,
    state_related: bool = False,
    state_new: bool = False,
    state_invalid: bool = False,
    logging: bool = False,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create a new firewall rule.

    Args:
        site_id: Site identifier
        name: Rule name
        action: Action to take (accept, drop, reject)
        src_address: Source IP address (CIDR notation or single IP)
        dst_address: Destination IP address (CIDR notation or single IP)
        protocol: Protocol (tcp, udp, icmp, all)
        port: Destination port number
        enabled: Enable the rule immediately
        ruleset: Ruleset to apply rule to (WAN_IN, WAN_OUT, LAN_IN, LAN_OUT, etc.)
        rule_index: Position in firewall chain (higher = lower priority)
        src_networkconf_id: Source network configuration ID (for inter-VLAN rules)
        src_networkconf_type: Source network type (default: NETv4)
        dst_networkconf_id: Destination network configuration ID (for inter-VLAN rules)
        dst_networkconf_type: Destination network type (default: NETv4)
        state_established: Match established connections
        state_related: Match related connections
        state_new: Match new connections
        state_invalid: Match invalid connections
        logging: Enable logging for matched traffic
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't create the rule

    Returns:
        Created firewall rule dictionary or dry-run result

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ValidationError: If validation fails
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "firewall operation", dry_run)

    # Validate action
    valid_actions = ["accept", "drop", "reject"]
    if action.lower() not in valid_actions:
        raise ValueError(f"Invalid action '{action}'. Must be one of: {valid_actions}")

    # Validate protocol if provided
    if protocol:
        valid_protocols = ["tcp", "udp", "icmp", "all"]
        if protocol.lower() not in valid_protocols:
            raise ValueError(f"Invalid protocol '{protocol}'. Must be one of: {valid_protocols}")

    # Build rule data
    rule_data: dict[str, Any] = {
        "name": name,
        "action": action.lower(),
        "enabled": enabled,
        "ruleset": ruleset,
        "rule_index": rule_index,
        "setting_preference": "auto",
        "src_networkconf_type": src_networkconf_type,
        "dst_networkconf_type": dst_networkconf_type,
        "state_new": state_new,
        "state_established": state_established,
        "state_invalid": state_invalid,
        "state_related": state_related,
        "logging": logging,
        "protocol_match_excepted": False,
    }

    if src_networkconf_id is not None:
        rule_data["src_networkconf_id"] = src_networkconf_id

    if dst_networkconf_id is not None:
        rule_data["dst_networkconf_id"] = dst_networkconf_id

    if src_address:
        rule_data["src_address"] = src_address

    if dst_address:
        rule_data["dst_address"] = dst_address

    if protocol:
        rule_data["protocol"] = protocol.lower()

    if port is not None:
        rule_data["dst_port"] = port

    # Log parameters for audit
    parameters = {
        "site_id": site_id,
        "name": name,
        "action": action,
        "src_address": src_address,
        "dst_address": dst_address,
        "protocol": protocol,
        "port": port,
        "enabled": enabled,
    }

    if dry_run:
        logger.info(f"DRY RUN: Would create firewall rule '{name}' in site '{site_id}'")
        await log_audit(
            operation="create_firewall_rule",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_create": rule_data}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)

        response = await client.post(
            client.legacy_path(site.name, "rest/firewallrule"), json_data=rule_data
        )
        # Client now auto-unwraps the "data" field, so response is the actual data
        if isinstance(response, list):
            created_rule: dict[str, Any] = response[0]
        else:
            data_list = response.get("data", [{}])
            created_rule = data_list[0] if isinstance(data_list, list) else {}

        logger.info(f"Created firewall rule '{name}' in site '{site_id}'")
        await log_audit(
            operation="create_firewall_rule",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return created_rule

    except Exception as e:
        logger.error(f"Failed to create firewall rule '{name}': {e}")
        await log_audit(
            operation="create_firewall_rule",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def update_firewall_rule(
    site_id: str,
    rule_id: str,
    name: str | None = None,
    action: str | None = None,
    src_address: str | None = None,
    dst_address: str | None = None,
    protocol: str | None = None,
    port: int | None = None,
    enabled: bool | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update an existing firewall rule.

    Args:
        site_id: Site identifier
        rule_id: Firewall rule ID
        name: New rule name
        action: New action (accept, drop, reject)
        src_address: New source network/IP
        dst_address: New destination network/IP
        protocol: New protocol (tcp, udp, icmp, all)
        port: New destination port
        enabled: Enable/disable the rule
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't update the rule

    Returns:
        Updated firewall rule dictionary or dry-run result

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If rule not found
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "firewall operation", dry_run)

    # Validate action if provided
    if action:
        valid_actions = ["accept", "drop", "reject"]
        if action.lower() not in valid_actions:
            raise ValueError(f"Invalid action '{action}'. Must be one of: {valid_actions}")

    # Validate protocol if provided
    if protocol:
        valid_protocols = ["tcp", "udp", "icmp", "all"]
        if protocol.lower() not in valid_protocols:
            raise ValueError(f"Invalid protocol '{protocol}'. Must be one of: {valid_protocols}")

    parameters = {
        "site_id": site_id,
        "rule_id": rule_id,
        "name": name,
        "action": action,
        "src_address": src_address,
        "dst_address": dst_address,
        "protocol": protocol,
        "port": port,
        "enabled": enabled,
    }

    if dry_run:
        logger.info(f"DRY RUN: Would update firewall rule '{rule_id}' in site '{site_id}'")
        await log_audit(
            operation="update_firewall_rule",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_update": parameters}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)

        # Get existing rule
        response = await client.get(client.legacy_path(site.name, "rest/firewallrule"))
        # Client now auto-unwraps the "data" field, so response is the actual data
        rules_data: list[dict[str, Any]] = (
            response if isinstance(response, list) else response.get("data", [])
        )

        existing_rule = None
        for rule in rules_data:
            if rule.get("_id") == rule_id:
                existing_rule = rule
                break

        if not existing_rule:
            raise ResourceNotFoundError("firewall_rule", rule_id)

        # Build update data
        update_data = existing_rule.copy()

        if name is not None:
            update_data["name"] = name
        if action is not None:
            update_data["action"] = action.lower()
        if src_address is not None:
            update_data["src_address"] = src_address
        if dst_address is not None:
            update_data["dst_address"] = dst_address
        if protocol is not None:
            update_data["protocol"] = protocol.lower()
        if port is not None:
            update_data["dst_port"] = port
        if enabled is not None:
            update_data["enabled"] = enabled

        response = await client.put(
            client.legacy_path(site.name, f"rest/firewallrule/{rule_id}"), json_data=update_data
        )
        # Client now auto-unwraps the "data" field, so response is the actual data
        if isinstance(response, list):
            updated_rule: dict[str, Any] = response[0]
        else:
            data_list = response.get("data", [{}])
            updated_rule = data_list[0] if isinstance(data_list, list) else {}

        logger.info(f"Updated firewall rule '{rule_id}' in site '{site_id}'")
        await log_audit(
            operation="update_firewall_rule",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return updated_rule

    except Exception as e:
        logger.error(f"Failed to update firewall rule '{rule_id}': {e}")
        await log_audit(
            operation="update_firewall_rule",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def delete_firewall_rule(
    site_id: str,
    rule_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Delete a firewall rule.

    Args:
        site_id: Site identifier
        rule_id: Firewall rule ID
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't delete the rule

    Returns:
        Deletion result dictionary

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If rule not found
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "firewall operation", dry_run)

    parameters = {"site_id": site_id, "rule_id": rule_id}

    if dry_run:
        logger.info(f"DRY RUN: Would delete firewall rule '{rule_id}' from site '{site_id}'")
        await log_audit(
            operation="delete_firewall_rule",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_delete": rule_id}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)

        # Verify rule exists before deleting
        response = await client.get(client.legacy_path(site.name, "rest/firewallrule"))
        # Client now auto-unwraps the "data" field, so response is the actual data
        rules_data: list[dict[str, Any]] = (
            response if isinstance(response, list) else response.get("data", [])
        )

        rule_exists = any(rule.get("_id") == rule_id for rule in rules_data)
        if not rule_exists:
            raise ResourceNotFoundError("firewall_rule", rule_id)

        await client.delete(client.legacy_path(site.name, f"rest/firewallrule/{rule_id}"))

        logger.info(f"Deleted firewall rule '{rule_id}' from site '{site_id}'")
        await log_audit(
            operation="delete_firewall_rule",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return {"success": True, "deleted_rule_id": rule_id}

    except Exception as e:
        logger.error(f"Failed to delete firewall rule '{rule_id}': {e}")
        await log_audit(
            operation="delete_firewall_rule",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


# =============================================================================
# Firewall Group CRUD
# =============================================================================


@provider.tool()
async def list_firewall_groups(
    site_id: str,
) -> list[dict[str, Any]]:
    """List firewall groups (IP/port groups) for a site.

    Args:
        site_id: Site identifier

    Returns:
        List of firewall group objects (name, group_type, group_members)
    """
    site_id = validate_site_id(site_id)

    client = get_network_client()
    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "rest/firewallgroup"))

    data: list[dict[str, Any]] = (
        response if isinstance(response, list) else response.get("data", [])
    )
    logger.info(f"Listed {len(data)} firewall groups for site '{site_id}'")
    return data


@provider.tool(annotations={"destructiveHint": True})
async def create_firewall_group(
    site_id: str,
    name: str,
    group_type: str,
    group_members: list[str],
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create a firewall group.

    Args:
        site_id: Site identifier
        name: Group name
        group_type: One of "address-group" (IPs/CIDRs), "port-group" (ports),
            or "ipv6-address-group"
        group_members: List of IP addresses, CIDRs, or port numbers as strings
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't create

    Returns:
        Created firewall group object
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "firewall operation", dry_run)

    parameters = {"site_id": site_id, "name": name, "group_type": group_type}

    if dry_run:
        logger.info(f"DRY RUN: Would create firewall group '{name}' in site '{site_id}'")
        await log_audit(
            operation="create_firewall_group",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {
            "dry_run": True,
            "would_create": {
                "name": name,
                "group_type": group_type,
                "group_members": group_members,
            },
        }

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)
        result = await client.post(
            client.legacy_path(site.name, "rest/firewallgroup"),
            json_data={
                "name": name,
                "group_type": group_type,
                "group_members": group_members,
            },
        )
        await log_audit(
            operation="create_firewall_group",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )
        return result if isinstance(result, dict) else {"data": result}
    except Exception as e:
        logger.error(f"Failed to create firewall group '{name}': {e}")
        await log_audit(
            operation="create_firewall_group",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def update_firewall_group(
    site_id: str,
    group_id: str,
    name: str | None = None,
    group_members: list[str] | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update a firewall group.

    Args:
        site_id: Site identifier
        group_id: Firewall group ID
        name: New group name (optional)
        group_members: New member list (optional)
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't update

    Returns:
        Updated firewall group object
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "firewall operation", dry_run)

    parameters = {"site_id": site_id, "group_id": group_id}

    if dry_run:
        logger.info(f"DRY RUN: Would update firewall group '{group_id}' in site '{site_id}'")
        await log_audit(
            operation="update_firewall_group",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_update": group_id}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)

        # Fetch existing to merge
        response = await client.get(client.legacy_path(site.name, "rest/firewallgroup"))
        groups_data: list[dict[str, Any]] = (
            response if isinstance(response, list) else response.get("data", [])
        )
        existing = next((g for g in groups_data if g.get("_id") == group_id), None)
        if existing is None:
            raise ResourceNotFoundError("firewall group", group_id)

        payload = dict(existing)
        if name is not None:
            payload["name"] = name
        if group_members is not None:
            payload["group_members"] = group_members

        result = await client.put(
            client.legacy_path(site.name, f"rest/firewallgroup/{group_id}"),
            json_data=payload,
        )
        await log_audit(
            operation="update_firewall_group",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )
        return result if isinstance(result, dict) else {"data": result}
    except Exception as e:
        logger.error(f"Failed to update firewall group '{group_id}': {e}")
        await log_audit(
            operation="update_firewall_group",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def delete_firewall_group(
    site_id: str,
    group_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Delete a firewall group.

    Args:
        site_id: Site identifier
        group_id: Firewall group ID
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't delete

    Returns:
        Deletion result dictionary
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "firewall operation", dry_run)

    parameters = {"site_id": site_id, "group_id": group_id}

    if dry_run:
        logger.info(f"DRY RUN: Would delete firewall group '{group_id}' from site '{site_id}'")
        await log_audit(
            operation="delete_firewall_group",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_delete": group_id}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)
        await client.delete(client.legacy_path(site.name, f"rest/firewallgroup/{group_id}"))
        await log_audit(
            operation="delete_firewall_group",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )
        return {"success": True, "group_id": group_id}
    except Exception as e:
        logger.error(f"Failed to delete firewall group '{group_id}': {e}")
        await log_audit(
            operation="delete_firewall_group",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise

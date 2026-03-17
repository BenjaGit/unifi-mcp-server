"""Port forwarding management MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import (
    ResourceNotFoundError,
    ValidationError,
    get_logger,
    log_audit,
    validate_confirmation,
    validate_ip_address,
    validate_limit_offset,
    validate_port,
    validate_site_id,
)

provider = LocalProvider()

__all__ = ["provider", "list_port_forwards", "create_port_forward", "delete_port_forward"]


@provider.tool()
async def list_port_forwards(
    site_id: str,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    """List all port forwarding rules in a site (read-only).

    Args:
        site_id: Site identifier
        settings: Application settings
        limit: Maximum number of rules to return
        offset: Number of rules to skip

    Returns:
        List of port forwarding rule dictionaries
    """
    site_id = validate_site_id(site_id)
    limit, offset = validate_limit_offset(limit, offset)
    logger = get_logger(__name__)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "rest/portforward"))
    rules_data: list[dict[str, Any]] = (
        response if isinstance(response, list) else response.get("data", [])
    )
    paginated = rules_data[offset : offset + limit]

    logger.info(f"Retrieved {len(paginated)} port forwarding rules for site '{site_id}'")
    return paginated


@provider.tool()
async def create_port_forward(
    site_id: str,
    name: str,
    dst_port: int,
    fwd_ip: str,
    fwd_port: int,
    protocol: str = "tcp_udp",
    src: str = "any",
    enabled: bool = True,
    log: bool = False,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create a port forwarding rule.

    Args:
        site_id: Site identifier
        name: Rule name/description
        dst_port: Destination port (external/WAN port)
        fwd_ip: Forward to IP address (internal/LAN)
        fwd_port: Forward to port (internal)
        settings: Application settings
        protocol: Protocol (tcp, udp, tcp_udp)
        src: Source restriction (any, or specific IP/network)
        enabled: Enable the rule immediately
        log: Enable logging for this rule
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't create the rule

    Returns:
        Created port forwarding rule dictionary or dry-run result

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ValidationError: If validation fails
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "port forwarding operation", dry_run)
    logger = get_logger(__name__)

    # Validate ports
    validate_port(dst_port)
    validate_port(fwd_port)

    # Validate forward IP
    validate_ip_address(fwd_ip)

    # Validate protocol
    valid_protocols = ["tcp", "udp", "tcp_udp"]
    if protocol not in valid_protocols:
        raise ValidationError(f"Invalid protocol '{protocol}'. Must be one of: {valid_protocols}")

    # Validate source if not "any"
    if src != "any":
        validate_ip_address(src.split("/")[0])  # Validate IP part of CIDR

    # Build port forward data
    pf_data = {
        "name": name,
        "dst_port": str(dst_port),
        "fwd": fwd_ip,
        "fwd_port": str(fwd_port),
        "proto": protocol,
        "src": src,
        "enabled": enabled,
        "log": log,
    }

    # Log parameters for audit
    parameters = {
        "site_id": site_id,
        "name": name,
        "dst_port": dst_port,
        "fwd_ip": fwd_ip,
        "fwd_port": fwd_port,
        "protocol": protocol,
        "src": src,
        "enabled": enabled,
    }

    if dry_run:
        logger.info(
            f"DRY RUN: Would create port forward '{name}' "
            f"({dst_port} -> {fwd_ip}:{fwd_port}) in site '{site_id}'"
        )
        await log_audit(
            operation="create_port_forward",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_create": pf_data}

    try:
        client = get_network_client()
        if not client.is_authenticated:
            await client.authenticate()

        site = await client.resolve_site(site_id)
        response = await client.post(
            client.legacy_path(site.name, "rest/portforward"), json_data=pf_data
        )
        created_rule: dict[str, Any] = (
            response[0] if isinstance(response, list) else response.get("data", [{}])[0]
        )

        logger.info(
            f"Created port forward '{name}' ({dst_port} -> {fwd_ip}:{fwd_port}) in site '{site_id}'"
        )
        await log_audit(
            operation="create_port_forward",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return created_rule

    except Exception as e:
        logger.error(f"Failed to create port forward '{name}': {e}")
        await log_audit(
            operation="create_port_forward",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def delete_port_forward(
    site_id: str,
    rule_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Delete a port forwarding rule.

    Args:
        site_id: Site identifier
        rule_id: Port forwarding rule ID
        settings: Application settings
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't delete the rule

    Returns:
        Deletion result dictionary

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If rule not found
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "port forwarding operation", dry_run)
    logger = get_logger(__name__)

    parameters = {"site_id": site_id, "rule_id": rule_id}

    if dry_run:
        logger.info(
            f"DRY RUN: Would delete port forwarding rule '{rule_id}' " f"from site '{site_id}'"
        )
        await log_audit(
            operation="delete_port_forward",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_delete": rule_id}

    try:
        client = get_network_client()
        if not client.is_authenticated:
            await client.authenticate()

        site = await client.resolve_site(site_id)

        response = await client.get(client.legacy_path(site.name, "rest/portforward"))
        rules_data: list[dict[str, Any]] = (
            response if isinstance(response, list) else response.get("data", [])
        )

        rule_exists = any(rule.get("_id") == rule_id for rule in rules_data)
        if not rule_exists:
            raise ResourceNotFoundError("port_forward_rule", rule_id)

        await client.delete(client.legacy_path(site.name, f"rest/portforward/{rule_id}"))

        logger.info(f"Deleted port forwarding rule '{rule_id}' from site '{site_id}'")
        await log_audit(
            operation="delete_port_forward",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return {"success": True, "deleted_rule_id": rule_id}

    except Exception as e:
        logger.error(f"Failed to delete port forwarding rule '{rule_id}': {e}")
        await log_audit(
            operation="delete_port_forward",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise

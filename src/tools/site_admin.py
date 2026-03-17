"""Site administration MCP tools - site CRUD and device migration."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import get_logger, log_audit, validate_confirmation, validate_site_id

provider = LocalProvider()

__all__ = ["provider", "create_site", "delete_site", "move_device"]


@provider.tool()
async def create_site(
    site_id: str,
    name: str,
    description: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create a new site."""
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "create site", dry_run)
    logger = get_logger(__name__)

    parameters = {"site_id": site_id, "name": name, "description": description}
    if dry_run:
        logger.info(f"DRY RUN: Would create site '{name}' via site '{site_id}'")
        await log_audit(
            operation="create_site",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_create": name}

    try:
        client = get_network_client()
        if not client.is_authenticated:
            await client.authenticate()

        site = await client.resolve_site(site_id)
        result = await client.post(
            client.legacy_path(site.name, "cmd/sitemgr"),
            json_data={"cmd": "add-site", "name": name, "desc": description},
        )
        await log_audit(
            operation="create_site", parameters=parameters, result="success", site_id=site_id
        )
        return result if isinstance(result, dict) else {"data": result}
    except Exception as exc:
        logger.error(f"Failed to create site '{name}': {exc}")
        await log_audit(
            operation="create_site", parameters=parameters, result="failed", site_id=site_id
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def delete_site(
    site_id: str,
    target_site_name: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Delete a site permanently."""
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "delete site", dry_run)
    logger = get_logger(__name__)

    parameters = {"site_id": site_id, "target_site_name": target_site_name}
    if dry_run:
        logger.info(f"DRY RUN: Would delete site '{target_site_name}' via site '{site_id}'")
        await log_audit(
            operation="delete_site",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_delete": target_site_name}

    try:
        client = get_network_client()
        if not client.is_authenticated:
            await client.authenticate()

        site = await client.resolve_site(site_id)
        await client.post(
            client.legacy_path(site.name, "cmd/sitemgr"),
            json_data={"cmd": "delete-site", "name": target_site_name},
        )
        await log_audit(
            operation="delete_site", parameters=parameters, result="success", site_id=site_id
        )
        return {"success": True, "site_name": target_site_name}
    except Exception as exc:
        logger.error(f"Failed to delete site '{target_site_name}': {exc}")
        await log_audit(
            operation="delete_site", parameters=parameters, result="failed", site_id=site_id
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def move_device(
    site_id: str,
    device_mac: str,
    target_site_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Move a device to a different site."""
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "move device", dry_run)
    logger = get_logger(__name__)

    parameters = {"site_id": site_id, "device_mac": device_mac, "target_site_id": target_site_id}
    if dry_run:
        logger.info(f"DRY RUN: Would move device '{device_mac}' to site '{target_site_id}'")
        await log_audit(
            operation="move_device",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_move": device_mac, "to_site": target_site_id}

    try:
        client = get_network_client()
        if not client.is_authenticated:
            await client.authenticate()

        site = await client.resolve_site(site_id)
        result = await client.post(
            client.legacy_path(site.name, "cmd/sitemgr"),
            json_data={"cmd": "move-device", "mac": device_mac, "site": target_site_id},
        )
        await log_audit(
            operation="move_device", parameters=parameters, result="success", site_id=site_id
        )
        return result if isinstance(result, dict) else {"success": True, "mac": device_mac}
    except Exception as exc:
        logger.error(f"Failed to move device '{device_mac}': {exc}")
        await log_audit(
            operation="move_device", parameters=parameters, result="failed", site_id=site_id
        )
        raise

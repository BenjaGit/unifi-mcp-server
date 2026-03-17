"""System control MCP tools - gateway reboot, poweroff, DPI counter reset."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import get_logger, log_audit, validate_confirmation, validate_site_id

provider = LocalProvider()

__all__ = ["provider", "reboot_gateway", "poweroff_gateway", "clear_dpi_counters"]


@provider.tool(annotations={"destructiveHint": True})
async def reboot_gateway(
    site_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Reboot the gateway for a site."""
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "reboot gateway", dry_run)
    logger = get_logger(__name__)

    parameters = {"site_id": site_id}
    if dry_run:
        logger.info(f"DRY RUN: Would reboot gateway for site '{site_id}'")
        await log_audit(
            operation="reboot_gateway",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_execute": "reboot"}

    try:
        client = get_network_client()
        if not client.is_authenticated:
            await client.authenticate()

        site = await client.resolve_site(site_id)
        await client.post(client.legacy_path(site.name, "cmd/system"), json_data={"cmd": "reboot"})
        await log_audit(
            operation="reboot_gateway", parameters=parameters, result="success", site_id=site_id
        )
        return {"success": True, "action": "reboot"}
    except Exception as exc:
        logger.error(f"Failed to reboot gateway: {exc}")
        await log_audit(
            operation="reboot_gateway", parameters=parameters, result="failed", site_id=site_id
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def poweroff_gateway(
    site_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Power off the gateway for a site."""
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "power off gateway", dry_run)
    logger = get_logger(__name__)

    parameters = {"site_id": site_id}
    if dry_run:
        logger.info(f"DRY RUN: Would power off gateway for site '{site_id}'")
        await log_audit(
            operation="poweroff_gateway",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_execute": "poweroff"}

    try:
        client = get_network_client()
        if not client.is_authenticated:
            await client.authenticate()

        site = await client.resolve_site(site_id)
        await client.post(
            client.legacy_path(site.name, "cmd/system"), json_data={"cmd": "poweroff"}
        )
        await log_audit(
            operation="poweroff_gateway", parameters=parameters, result="success", site_id=site_id
        )
        return {"success": True, "action": "poweroff"}
    except Exception as exc:
        logger.error(f"Failed to power off gateway: {exc}")
        await log_audit(
            operation="poweroff_gateway", parameters=parameters, result="failed", site_id=site_id
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def clear_dpi_counters(
    site_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Clear DPI (Deep Packet Inspection) counters for a site."""
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "clear DPI counters", dry_run)
    logger = get_logger(__name__)

    parameters = {"site_id": site_id}
    if dry_run:
        logger.info(f"DRY RUN: Would clear DPI counters for site '{site_id}'")
        await log_audit(
            operation="clear_dpi_counters",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_execute": "clear_dpi"}

    try:
        client = get_network_client()
        if not client.is_authenticated:
            await client.authenticate()

        site = await client.resolve_site(site_id)
        await client.post(
            client.legacy_path(site.name, "cmd/system"), json_data={"cmd": "clear-dpi"}
        )
        await log_audit(
            operation="clear_dpi_counters", parameters=parameters, result="success", site_id=site_id
        )
        return {"success": True, "action": "clear_dpi"}
    except Exception as exc:
        logger.error(f"Failed to clear DPI counters: {exc}")
        await log_audit(
            operation="clear_dpi_counters", parameters=parameters, result="failed", site_id=site_id
        )
        raise

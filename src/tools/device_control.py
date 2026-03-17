"""Device control MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import (
    ResourceNotFoundError,
    get_logger,
    log_audit,
    sanitize_log_message,
    validate_confirmation,
    validate_mac_address,
    validate_site_id,
)

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = [
    "provider",
    "restart_device",
    "locate_device",
    "upgrade_device",
    "delete_device",
    "force_provision_device",
    "run_speedtest",
    "get_speedtest_status",
    "trigger_spectrum_scan",
    "migrate_device",
    "cancel_device_migration",
]


@provider.tool()
async def restart_device(
    site_id: str,
    device_mac: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Restart a UniFi device.

    Args:
        site_id: Site identifier
        device_mac: Device MAC address
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't restart the device

    Returns:
        Restart result dictionary

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If device not found
    """
    site_id = validate_site_id(site_id)
    device_mac = validate_mac_address(device_mac)
    validate_confirmation(confirm, "device control operation", dry_run)

    parameters = {"site_id": site_id, "device_mac": device_mac}

    if dry_run:
        logger.info(
            sanitize_log_message(
                f"DRY RUN: Would restart device '{device_mac}' in site '{site_id}'"
            )
        )
        await log_audit(
            operation="restart_device",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_restart": device_mac}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)

        # Look up device by MAC via Integration API (returns UUID-format IDs)
        response = await client.get(client.integration_path(site.uuid, "devices"))
        devices_data: list[dict[str, Any]] = (
            response if isinstance(response, list) else response.get("data", [])
        )

        device = next(
            (
                d
                for d in devices_data
                if validate_mac_address(d.get("macAddress", d.get("mac", ""))) == device_mac
            ),
            None,
        )
        if not device:
            raise ResourceNotFoundError("device", device_mac)

        device_id = device["id"]

        # Restart the device via Integration API (action must be uppercase)
        restart_data = {"action": "RESTART"}
        await client.post(
            client.integration_path(site.uuid, f"devices/{device_id}/actions"),
            json_data=restart_data,
        )

        logger.info(
            sanitize_log_message(f"Initiated restart for device '{device_mac}' in site '{site_id}'")
        )
        await log_audit(
            operation="restart_device",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return {
            "success": True,
            "device_mac": device_mac,
            "message": "Device restart initiated",
        }

    except Exception as e:
        logger.error(sanitize_log_message(f"Failed to restart device '{device_mac}': {e}"))
        await log_audit(
            operation="restart_device",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool()
async def locate_device(
    site_id: str,
    device_mac: str,
    enabled: bool = True,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Enable or disable LED locate mode on a device.

    Args:
        site_id: Site identifier
        device_mac: Device MAC address
        enabled: Enable (True) or disable (False) locate mode
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't change locate state

    Returns:
        Locate result dictionary

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If device not found
    """
    site_id = validate_site_id(site_id)
    device_mac = validate_mac_address(device_mac)
    validate_confirmation(confirm, "device control operation", dry_run)

    parameters = {"site_id": site_id, "device_mac": device_mac, "enabled": enabled}

    action = "enable" if enabled else "disable"

    if dry_run:
        logger.info(
            sanitize_log_message(
                f"DRY RUN: Would {action} locate mode for device '{device_mac}' "
                f"in site '{site_id}'"
            )
        )
        await log_audit(
            operation="locate_device",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, f"would_{action}": device_mac}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)

        # Locate is not supported via Integration API — use legacy cmd/devmgr
        cmd = "set-locate" if enabled else "unset-locate"
        locate_data = {"cmd": cmd, "mac": device_mac}
        await client.post(
            client.legacy_path(site.name, "cmd/devmgr"),
            json_data=locate_data,
        )

        logger.info(
            sanitize_log_message(
                f"{action.capitalize()}d locate mode for device '{device_mac}' "
                f"in site '{site_id}'"
            )
        )
        await log_audit(
            operation="locate_device",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return {
            "success": True,
            "device_mac": device_mac,
            "locate_enabled": enabled,
            "message": f"Locate mode {action}d",
        }

    except Exception as e:
        logger.error(
            sanitize_log_message(f"Failed to {action} locate for device '{device_mac}': {e}")
        )
        await log_audit(
            operation="locate_device",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def delete_device(
    site_id: str,
    device_mac: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Remove a device from the UniFi controller.

    WARNING: This removes the device from the controller. The device will need
    to be physically re-adopted to be managed again.

    Args:
        site_id: Site identifier
        device_mac: Device MAC address
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't delete the device

    Returns:
        Deletion result dictionary

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If device not found
    """
    site_id = validate_site_id(site_id)
    device_mac = validate_mac_address(device_mac)
    validate_confirmation(confirm, "device control operation", dry_run)

    parameters = {"site_id": site_id, "device_mac": device_mac}

    if dry_run:
        logger.info(
            sanitize_log_message(
                f"DRY RUN: Would delete device '{device_mac}' from site '{site_id}'"
            )
        )
        await log_audit(
            operation="delete_device",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_delete": device_mac}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)

        # Look up device by MAC via Integration API (returns UUID-format IDs)
        response = await client.get(client.integration_path(site.uuid, "devices"))
        devices_data: list[dict[str, Any]] = (
            response if isinstance(response, list) else response.get("data", [])
        )

        device = next(
            (
                d
                for d in devices_data
                if validate_mac_address(d.get("macAddress", d.get("mac", ""))) == device_mac
            ),
            None,
        )
        if not device:
            raise ResourceNotFoundError("device", device_mac)

        device_id = device["id"]
        device_name = device.get("name", "Unknown")

        await client.delete(client.integration_path(site.uuid, f"devices/{device_id}"))

        logger.info(
            sanitize_log_message(
                f"Removed device '{device_name}' ({device_mac}) from site '{site_id}'"
            )
        )
        await log_audit(
            operation="delete_device",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return {
            "success": True,
            "device_mac": device_mac,
            "device_name": device_name,
            "message": f"Device '{device_name}' removed from controller",
        }

    except Exception as e:
        logger.error(sanitize_log_message(f"Failed to delete device '{device_mac}': {e}"))
        await log_audit(
            operation="delete_device",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool()
async def upgrade_device(
    site_id: str,
    device_mac: str,
    firmware_url: str | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Trigger firmware upgrade for a device.

    Args:
        site_id: Site identifier
        device_mac: Device MAC address
        firmware_url: Optional custom firmware URL (uses latest if not provided)
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't initiate upgrade

    Returns:
        Upgrade result dictionary

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If device not found
    """
    site_id = validate_site_id(site_id)
    device_mac = validate_mac_address(device_mac)
    validate_confirmation(confirm, "device control operation", dry_run)
    parameters = {
        "site_id": site_id,
        "device_mac": device_mac,
        "firmware_url": firmware_url,
    }

    if dry_run:
        logger.info(
            sanitize_log_message(
                f"DRY RUN: Would initiate firmware upgrade for device '{device_mac}' "
                f"in site '{site_id}'"
            )
        )
        await log_audit(
            operation="upgrade_device",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_upgrade": device_mac}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)

        # Look up device by MAC via legacy API for version info
        response = await client.get(client.legacy_path(site.name, "devices"))
        devices_data: list[dict[str, Any]] = (
            response if isinstance(response, list) else response.get("data", [])
        )

        device = next(
            (d for d in devices_data if validate_mac_address(d.get("mac", "")) == device_mac),
            None,
        )
        if not device:
            raise ResourceNotFoundError("device", device_mac)

        # Upgrade via legacy cmd/devmgr (not supported via Integration API)
        upgrade_data: dict[str, Any] = {"cmd": "upgrade", "mac": device_mac}
        if firmware_url:
            upgrade_data["url"] = firmware_url

        await client.post(
            client.legacy_path(site.name, "cmd/devmgr"),
            json_data=upgrade_data,
        )

        logger.info(
            sanitize_log_message(
                f"Initiated firmware upgrade for device '{device_mac}' " f"in site '{site_id}'"
            )
        )
        await log_audit(
            operation="upgrade_device",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return {
            "success": True,
            "device_mac": device_mac,
            "message": "Firmware upgrade initiated",
            "current_version": device.get("version"),
        }

    except Exception as e:
        logger.error(sanitize_log_message(f"Failed to upgrade device '{device_mac}': {e}"))
        await log_audit(
            operation="upgrade_device",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def force_provision_device(
    site_id: str,
    device_mac: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Force provision a UniFi device, pushing current config immediately.

    Args:
        site_id: Site identifier
        device_mac: Device MAC address
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't provision

    Returns:
        Force provision result dictionary
    """
    site_id = validate_site_id(site_id)
    device_mac = validate_mac_address(device_mac)
    validate_confirmation(confirm, "force provision device", dry_run)
    parameters = {"site_id": site_id, "device_mac": device_mac}

    if dry_run:
        logger.info(
            sanitize_log_message(
                f"DRY RUN: Would force provision device '{device_mac}' in site '{site_id}'"
            )
        )
        await log_audit(
            operation="force_provision_device",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_provision": device_mac}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)
        await client.post(
            client.legacy_path(site.name, "cmd/devmgr"),
            json_data={"cmd": "force-provision", "mac": device_mac},
        )
        logger.info(
            sanitize_log_message(f"Force provisioned device '{device_mac}' in site '{site_id}'")
        )
        await log_audit(
            operation="force_provision_device",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )
        return {
            "success": True,
            "device_mac": device_mac,
            "message": "Device force-provisioned",
        }
    except Exception as e:
        logger.error(sanitize_log_message(f"Failed to force provision device '{device_mac}': {e}"))
        await log_audit(
            operation="force_provision_device",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def run_speedtest(
    site_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Run a WAN speed test on the gateway.

    Args:
        site_id: Site identifier
        confirm: Confirmation flag (must be True to execute)

    Returns:
        Speed test start confirmation. Use get_speedtest_status to poll results.
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "run speed test", dry_run)

    parameters = {"site_id": site_id}

    if dry_run:
        logger.info(sanitize_log_message(f"DRY RUN: Would start speed test in site '{site_id}'"))
        await log_audit(
            operation="run_speedtest",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_execute": "speedtest"}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)
        await client.post(
            client.legacy_path(site.name, "cmd/devmgr"), json_data={"cmd": "speedtest"}
        )
        logger.info(sanitize_log_message(f"Started speed test in site '{site_id}'"))
        await log_audit(
            operation="run_speedtest",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )
        return {
            "success": True,
            "message": "Speed test started. Use get_speedtest_status to check results.",
        }
    except Exception as e:
        logger.error(sanitize_log_message(f"Failed to start speed test in site '{site_id}': {e}"))
        await log_audit(
            operation="run_speedtest",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool()
async def get_speedtest_status(
    site_id: str,
) -> dict[str, Any]:
    """Get current speed test status and results.

    Args:
        site_id: Site identifier

    Returns:
        Speed test status with xput_download, xput_upload, latency fields.
    """
    site_id = validate_site_id(site_id)

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)
        response = await client.post(
            client.legacy_path(site.name, "cmd/devmgr"),
            json_data={"cmd": "speedtest-status"},
        )
        logger.info(sanitize_log_message(f"Retrieved speed test status for site '{site_id}'"))
        return response if isinstance(response, dict) else {"data": response}
    except Exception as e:
        logger.error(
            sanitize_log_message(f"Failed to get speed test status for site '{site_id}': {e}")
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def trigger_spectrum_scan(
    site_id: str,
    ap_mac: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Trigger an RF spectrum scan on an access point.

    Args:
        site_id: Site identifier
        ap_mac: Access point MAC address
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't trigger

    Returns:
        Spectrum scan trigger confirmation
    """
    site_id = validate_site_id(site_id)
    ap_mac = validate_mac_address(ap_mac)
    validate_confirmation(confirm, "trigger spectrum scan", dry_run)

    parameters = {"site_id": site_id, "ap_mac": ap_mac}

    if dry_run:
        logger.info(
            sanitize_log_message(
                f"DRY RUN: Would trigger spectrum scan on AP '{ap_mac}' in site '{site_id}'"
            )
        )
        await log_audit(
            operation="trigger_spectrum_scan",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_scan_ap": ap_mac}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)
        await client.post(
            client.legacy_path(site.name, "cmd/devmgr"),
            json_data={"cmd": "spectrum-scan", "mac": ap_mac},
        )
        logger.info(
            sanitize_log_message(f"Triggered spectrum scan on AP '{ap_mac}' in site '{site_id}'")
        )
        await log_audit(
            operation="trigger_spectrum_scan",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )
        return {
            "success": True,
            "ap_mac": ap_mac,
            "message": "Spectrum scan triggered on AP",
        }
    except Exception as e:
        logger.error(sanitize_log_message(f"Failed to trigger spectrum scan on AP '{ap_mac}': {e}"))
        await log_audit(
            operation="trigger_spectrum_scan",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def migrate_device(
    site_id: str,
    device_mac: str,
    inform_url: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Migrate a device to a different controller.

    Args:
        site_id: Site identifier
        device_mac: MAC address of the device to migrate
        inform_url: Inform URL of the target controller
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't migrate

    Returns:
        Result dictionary
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "migrate device", dry_run)

    parameters = {"site_id": site_id, "device_mac": device_mac, "inform_url": inform_url}

    if dry_run:
        logger.info(
            sanitize_log_message(f"DRY RUN: Would migrate device '{device_mac}' to '{inform_url}'")
        )
        await log_audit(
            operation="migrate_device",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_migrate": device_mac, "inform_url": inform_url}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)
        result = await client.post(
            client.legacy_path(site.name, "cmd/devmgr"),
            json_data={"cmd": "migrate", "mac": device_mac, "inform_url": inform_url},
        )
        await log_audit(
            operation="migrate_device",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )
        return result if isinstance(result, dict) else {"success": True, "mac": device_mac}
    except Exception as e:
        logger.error(sanitize_log_message(f"Failed to migrate device '{device_mac}': {e}"))
        await log_audit(
            operation="migrate_device",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool()
async def cancel_device_migration(
    site_id: str,
    device_mac: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Cancel an in-progress device migration.

    Args:
        site_id: Site identifier
        device_mac: MAC address of the device to cancel migration for
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't cancel

    Returns:
        Result dictionary
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "cancel device migration", dry_run)
    parameters = {"site_id": site_id, "device_mac": device_mac}

    if dry_run:
        logger.info(
            sanitize_log_message(f"DRY RUN: Would cancel migration for device '{device_mac}'")
        )
        await log_audit(
            operation="cancel_device_migration",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_cancel_migration": device_mac}

    try:
        client = get_network_client()
        site = await client.resolve_site(site_id)
        result = await client.post(
            client.legacy_path(site.name, "cmd/devmgr"),
            json_data={"cmd": "cancel-migrate", "mac": device_mac},
        )
        await log_audit(
            operation="cancel_device_migration",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )
        return result if isinstance(result, dict) else {"success": True, "mac": device_mac}
    except Exception as e:
        logger.error(
            sanitize_log_message(f"Failed to cancel migration for device '{device_mac}': {e}")
        )
        await log_audit(
            operation="cancel_device_migration",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise

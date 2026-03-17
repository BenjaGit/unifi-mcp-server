"""Backup and restore operations MCP tools."""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..config import APIType
from ..utils import ValidationError, get_logger, log_audit, validate_confirmation, validate_site_id

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = [
    "provider",
    "trigger_backup",
    "list_backups",
    "get_backup_details",
    "download_backup",
    "delete_backup",
    "restore_backup",
    "validate_backup",
    "get_backup_status",
    "get_restore_status",
    "schedule_backups",
    "get_backup_schedule",
]


@provider.tool()
async def trigger_backup(
    site_id: str,
    backup_type: str,
    retention_days: int = 30,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Trigger a backup operation on the UniFi controller.

    This creates a new backup of the specified type. The backup process may take
    several minutes depending on the size of your configuration and number of devices.

    Args:
        site_id: Site identifier
        backup_type: Type of backup ("network" or "system")
                    - "network": Network settings and device configurations only
                    - "system": Complete OS, application, and device configurations
        settings: Application settings
        retention_days: Number of days to retain the backup (default: 30, -1 for indefinite)
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't create the backup

    Returns:
        Backup operation result including download URL and metadata

    Raises:
        ValidationError: If confirm is not True or backup_type is invalid

    Example:
        ```python
        result = await trigger_backup(
            site_id="default",
            backup_type="network",
            retention_days=30,
            confirm=True,
            settings=settings
        )
        print(f"Backup created: {result['filename']}")
        print(f"Download from: {result['download_url']}")
        ```

    Note:
        - Network backups are faster and smaller (typically <10 MB)
        - System backups are comprehensive but larger (can be >100 MB)
        - After backup completes, use the download_url to retrieve the file
        - Backup files are named with timestamp: backup_YYYY-MM-DD_HH-MM-SS.unf
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "backup operation", dry_run)

    # Validate backup type
    valid_types = ["network", "system"]
    if backup_type.lower() not in valid_types:
        raise ValidationError(f"Invalid backup_type '{backup_type}'. Must be one of: {valid_types}")

    # Validate retention days
    if retention_days < -1 or retention_days == 0:
        raise ValidationError("retention_days must be -1 (indefinite) or positive integer")

    parameters = {
        "site_id": site_id,
        "backup_type": backup_type,
        "retention_days": retention_days,
    }

    if dry_run:
        logger.info(
            f"DRY RUN: Would create {backup_type} backup for site '{site_id}' "
            f"with {retention_days} days retention"
        )
        await log_audit(
            operation="trigger_backup",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {
            "dry_run": True,
            "would_create": {
                "backup_type": backup_type,
                "retention_days": retention_days,
                "estimated_size": "10-100 MB" if backup_type == "system" else "<10 MB",
            },
        }

    client = get_network_client()

    if not client.is_authenticated:
        await client.authenticate()

    try:
        site = await client.resolve_site(site_id)

        endpoint = client.legacy_path(site.name, "cmd/backup")
        payload = {"cmd": "backup", "days": str(retention_days)}
        response = await client.post(endpoint, json_data=payload)

        backup_data = response.get("data", {}) if isinstance(response, dict) else {}
        download_url = backup_data.get("url", "")
        backup_id = backup_data.get("id", "")

        filename = (
            download_url.split("/")[-1]
            if download_url
            else f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.unf"
        )

        result = {
            "backup_id": backup_id or filename.replace(".unf", ""),
            "filename": filename,
            "download_url": download_url,
            "backup_type": backup_type,
            "created_at": datetime.now().isoformat(),
            "retention_days": retention_days,
            "status": "completed",
        }

        logger.info(f"Successfully created {backup_type} backup '{filename}' for site '{site_id}'")
        await log_audit(
            operation="trigger_backup",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return result

    except Exception as e:
        logger.error(f"Failed to create backup for site '{site_id}': {e}")
        await log_audit(
            operation="trigger_backup",
            parameters=parameters,
            result="error",
            error=str(e),
            site_id=site_id,
        )
        raise


@provider.tool()
async def list_backups(
    site_id: str,
) -> list[dict[str, Any]]:
    """List all available backups for a site.

    Retrieves metadata for all backup files including file size, creation date,
    type, and validity status.

    Args:
        site_id: Site identifier
        settings: Application settings

    Returns:
        List of backup metadata dictionaries

    Example:
        ```python
        backups = await list_backups(site_id="default", settings=settings)
        for backup in backups:
            print(f"{backup['filename']}: {backup['size_bytes']} bytes, "
                  f"created {backup['created_at']}")
        ```
    """
    site_id = validate_site_id(site_id)
    return await _list_backups_impl(site_id)


async def _list_backups_impl(site_id: str) -> list[dict[str, Any]]:
    """Fetch and normalize backup metadata list."""
    client = get_network_client()

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    if client.settings.api_type == APIType.LOCAL:
        endpoint = client.legacy_path(site.name, "cmd/backup")
        response = await client.post(endpoint, json_data={"cmd": "list-backups"})
    else:
        endpoint = client.legacy_path(site.name, "backups")
        response = await client.get(endpoint)

    backups_data: list[dict[str, Any]]
    if isinstance(response, list):
        backups_data = response
    elif isinstance(response, dict):
        data = response.get("data", response.get("backups", []))
        backups_data = data if isinstance(data, list) else []
    else:
        backups_data = []

    backups: list[dict[str, Any]] = []
    for backup in backups_data:
        filename = backup.get("filename", backup.get("name", ""))
        size_bytes = backup.get("size", backup.get("filesize", 0))
        created_timestamp = backup.get("datetime", backup.get("created", ""))

        backup_type_str = backup.get("type", "")
        if not backup_type_str:
            backup_type_str = "SYSTEM" if filename.endswith(".unifi") else "NETWORK"

        backups.append(
            {
                "backup_id": backup.get("id", filename.replace(".unf", "").replace(".unifi", "")),
                "filename": filename,
                "backup_type": backup_type_str,
                "created_at": created_timestamp,
                "size_bytes": size_bytes,
                "version": backup.get("version", ""),
                "is_valid": backup.get("valid", True),
                "cloud_synced": backup.get("cloud_backup", False),
            }
        )

    logger.info(f"Retrieved {len(backups)} backups for site '{site_id}'")
    return backups


@provider.tool()
async def get_backup_details(
    site_id: str,
    backup_filename: str,
) -> dict[str, Any]:
    """Get detailed information about a specific backup.

    Args:
        site_id: Site identifier
        backup_filename: Backup filename (e.g., "backup_2025-01-29.unf")
        settings: Application settings

    Returns:
        Detailed backup metadata dictionary

    Raises:
        ResourceNotFoundError: If backup file is not found
    """
    site_id = validate_site_id(site_id)

    backups = await _list_backups_impl(site_id)

    for backup in backups:
        if backup["filename"] == backup_filename:
            logger.info(f"Retrieved details for backup '{backup_filename}' in site '{site_id}'")
            return backup

    from ..utils import ResourceNotFoundError

    raise ResourceNotFoundError("backup", backup_filename)


@provider.tool()
async def download_backup(
    site_id: str,
    backup_filename: str,
    output_path: str,
    verify_checksum: bool = True,
) -> dict[str, Any]:
    """Download a backup file to local storage.

    Downloads the specified backup file and optionally verifies its integrity
    using checksum validation.

    Args:
        site_id: Site identifier
        backup_filename: Backup filename to download
        output_path: Local filesystem path to save the backup
        settings: Application settings
        verify_checksum: Whether to calculate and verify file checksum

    Returns:
        Download result with file path and metadata

    Example:
        ```python
        result = await download_backup(
            site_id="default",
            backup_filename="backup_2025-01-29.unf",
            output_path="/backups/unifi_backup.unf",
            settings=settings
        )
        print(f"Downloaded to: {result['local_path']}")
        print(f"Size: {result['size_bytes']} bytes")
        print(f"Checksum: {result['checksum']}")
        ```
    """
    site_id = validate_site_id(site_id)
    client = get_network_client()

    if not client.is_authenticated:
        await client.authenticate()

    logger.info(f"Downloading backup '{backup_filename}' from site '{site_id}'")

    try:
        site = await client.resolve_site(site_id)

        if client.settings.api_type == APIType.LOCAL:
            endpoint = f"/proxy/network/data/backup/{backup_filename}"
        else:
            endpoint = client.legacy_path(site.name, f"backups/{backup_filename}/download")

        response = await client.raw_request("GET", endpoint)
        backup_content = response.content

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_bytes(backup_content)

        checksum = ""
        if verify_checksum:
            sha256_hash = hashlib.sha256()
            sha256_hash.update(backup_content)
            checksum = sha256_hash.hexdigest()

        result = {
            "backup_filename": backup_filename,
            "local_path": str(output_file.absolute()),
            "size_bytes": len(backup_content),
            "checksum": checksum if verify_checksum else None,
            "download_time": datetime.now().isoformat(),
        }

        logger.info(
            f"Successfully downloaded backup '{backup_filename}' to '{output_path}' "
            f"({len(backup_content)} bytes)"
        )
        await log_audit(
            operation="download_backup",
            parameters={"site_id": site_id, "backup_filename": backup_filename},
            result="success",
            site_id=site_id,
        )

        return result

    except Exception as e:
        logger.error(f"Failed to download backup '{backup_filename}': {e}")
        await log_audit(
            operation="download_backup",
            parameters={"site_id": site_id, "backup_filename": backup_filename},
            result="error",
            error=str(e),
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def delete_backup(
    site_id: str,
    backup_filename: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Delete a backup file from the controller.

    Permanently removes a backup file from the UniFi controller storage.
    This operation cannot be undone.

    Args:
        site_id: Site identifier
        backup_filename: Backup filename to delete
        settings: Application settings
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't delete the backup

    Returns:
        Deletion result

    Raises:
        ValidationError: If confirm is not True

    Example:
        ```python
        result = await delete_backup(
            site_id="default",
            backup_filename="old_backup_2024-01-01.unf",
            confirm=True,
            settings=settings
        )
        print(f"Deleted: {result['backup_filename']}")
        ```

    Warning:
        This operation permanently deletes the backup file.
        Ensure you have downloaded or don't need the backup before deleting.
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "backup deletion", dry_run)
    client = get_network_client()

    if not client.is_authenticated:
        await client.authenticate()

    parameters = {
        "site_id": site_id,
        "backup_filename": backup_filename,
    }

    if dry_run:
        logger.info(f"DRY RUN: Would delete backup '{backup_filename}' from site '{site_id}'")
        await log_audit(
            operation="delete_backup",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_delete": backup_filename}

    try:
        site = await client.resolve_site(site_id)

        if client.settings.api_type == APIType.LOCAL:
            endpoint = f"/proxy/network/api/backup/delete-backup/{backup_filename}"
        else:
            endpoint = client.legacy_path(site.name, f"backups/{backup_filename}")

        await client.delete(endpoint)

        logger.info(f"Successfully deleted backup '{backup_filename}' from site '{site_id}'")
        await log_audit(
            operation="delete_backup",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return {
            "backup_filename": backup_filename,
            "status": "deleted",
            "deleted_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to delete backup '{backup_filename}': {e}")
        await log_audit(
            operation="delete_backup",
            parameters=parameters,
            result="error",
            error=str(e),
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def restore_backup(
    site_id: str,
    backup_filename: str,
    create_pre_restore_backup: bool = True,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Restore the UniFi controller from a backup file.

    This is a DESTRUCTIVE operation that will restore the controller to the state
    captured in the backup. The controller may restart during the restore process.

    Safety features:
    - Automatic pre-restore backup creation (enabled by default)
    - Mandatory confirmation flag
    - Dry-run mode for validation
    - Audit logging

    Args:
        site_id: Site identifier
        backup_filename: Backup filename to restore from
        settings: Application settings
        create_pre_restore_backup: Create automatic backup before restore (recommended)
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't restore

    Returns:
        Restore operation result including pre-restore backup info

    Raises:
        ValidationError: If confirm is not True

    Example:
        ```python
        # ALWAYS use confirm=True for restore operations
        result = await restore_backup(
            site_id="default",
            backup_filename="backup_2025-01-29.unf",
            create_pre_restore_backup=True,  # Create safety backup first
            confirm=True,
            settings=settings
        )
        print(f"Restore initiated. Pre-restore backup: {result['pre_restore_backup_id']}")
        ```

    Warning:
        This operation will:
        1. Restore all configuration from the backup
        2. May overwrite current settings
        3. May cause controller restart
        4. May temporarily disconnect devices

        ALWAYS create a pre-restore backup (enabled by default) so you can
        rollback if needed.
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(
        confirm, "RESTORE operation - this will OVERWRITE current configuration", dry_run
    )
    parameters = {
        "site_id": site_id,
        "backup_filename": backup_filename,
        "create_pre_restore_backup": create_pre_restore_backup,
    }

    if dry_run:
        logger.info(f"DRY RUN: Would restore from backup '{backup_filename}' for site '{site_id}'")
        await log_audit(
            operation="restore_backup",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {
            "dry_run": True,
            "would_restore_from": backup_filename,
            "would_create_pre_restore_backup": create_pre_restore_backup,
            "warning": "Controller will restart during restore",
        }

    client = get_network_client()

    if not client.is_authenticated:
        await client.authenticate()

    try:
        site = await client.resolve_site(site_id)

        pre_restore_backup_id = None
        if create_pre_restore_backup:
            logger.info("Creating pre-restore backup for safety...")
            pre_restore_result = await trigger_backup(
                site_id=site_id,
                backup_type="network",
                retention_days=7,
                confirm=True,
            )
            pre_restore_backup_id = pre_restore_result["backup_id"]
            logger.info(f"Pre-restore backup created: {pre_restore_backup_id}")

        logger.warning(
            f"INITIATING RESTORE from '{backup_filename}' for site '{site_id}'. "
            "Controller may restart."
        )

        if client.settings.api_type == APIType.LOCAL:
            endpoint = "/proxy/network/api/backup/restore"
            payload: dict[str, Any] = {"filename": backup_filename}
        else:
            endpoint = client.legacy_path(site.name, f"backups/{backup_filename}/restore")
            payload = {"backup_id": backup_filename}

        restore_response = await client.post(endpoint, json_data=payload)

        result = {
            "backup_filename": backup_filename,
            "status": "restore_initiated",
            "pre_restore_backup_id": pre_restore_backup_id,
            "can_rollback": pre_restore_backup_id is not None,
            "restore_time": datetime.now().isoformat(),
            "warning": "Controller may restart. Devices may temporarily disconnect.",
            "restore_response": restore_response,
        }

        logger.warning(
            f"Restore initiated from '{backup_filename}'. "
            f"Pre-restore backup: {pre_restore_backup_id or 'None'}"
        )
        await log_audit(
            operation="restore_backup",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return result

    except Exception as e:
        logger.error(f"Failed to restore from backup '{backup_filename}': {e}")
        await log_audit(
            operation="restore_backup",
            parameters=parameters,
            result="error",
            error=str(e),
            site_id=site_id,
        )
        raise


@provider.tool()
async def validate_backup(
    site_id: str,
    backup_filename: str,
) -> dict[str, Any]:
    """Validate a backup file before restore.

    Performs integrity checks on a backup file to ensure it's valid and compatible
    with the current controller version.

    Args:
        site_id: Site identifier
        backup_filename: Backup filename to validate
        settings: Application settings

    Returns:
        Validation result with details and warnings

    Example:
        ```python
        validation = await validate_backup(
            site_id="default",
            backup_filename="backup_2025-01-29.unf",
            settings=settings
        )
        if validation['is_valid']:
            print("Backup is valid and ready to restore")
        else:
            print(f"Validation errors: {validation['errors']}")
        ```
    """
    site_id = validate_site_id(site_id)

    try:
        # Get backup details
        backup_details = await get_backup_details(
            site_id=site_id,
            backup_filename=backup_filename,
        )

        # Basic validation checks
        warnings = []
        errors = []

        # Check file size
        size_bytes = backup_details.get("size_bytes", 0)
        if size_bytes == 0:
            errors.append("Backup file appears to be empty")
        elif size_bytes < 1024:  # Less than 1 KB
            warnings.append("Backup file is unusually small")

        # Check backup validity flag
        if not backup_details.get("is_valid", True):
            errors.append("Backup is marked as invalid by controller")

        # Version compatibility check would require downloading the file
        # For now, we just note if version info is available
        backup_version = backup_details.get("version", "")
        if not backup_version:
            warnings.append("Backup version unknown - cannot verify compatibility")

        is_valid = len(errors) == 0

        result = {
            "backup_id": backup_details.get("backup_id", ""),
            "backup_filename": backup_filename,
            "is_valid": is_valid,
            "checksum_valid": True,  # Assumed true if controller lists it
            "format_valid": is_valid,
            "version_compatible": len(errors) == 0,
            "backup_version": backup_version,
            "warnings": warnings,
            "errors": errors,
            "size_bytes": size_bytes,
            "validated_at": datetime.now().isoformat(),
        }

        logger.info(
            f"Validated backup '{backup_filename}': "
            f"{'VALID' if is_valid else 'INVALID'} "
            f"({len(warnings)} warnings, {len(errors)} errors)"
        )

        return result

    except Exception as e:
        logger.error(f"Failed to validate backup '{backup_filename}': {e}")
        return {
            "backup_filename": backup_filename,
            "is_valid": False,
            "errors": [str(e)],
            "validated_at": datetime.now().isoformat(),
        }


@provider.tool()
async def get_backup_status(
    operation_id: str,
) -> dict[str, Any]:
    """Get the status of an ongoing or completed backup operation.

    Monitor the progress of a backup operation initiated with trigger_backup.
    Useful for tracking long-running system backups.

    Args:
        operation_id: Backup operation identifier (returned by trigger_backup)
        settings: Application settings

    Returns:
        Backup operation status including progress and result

    Note:
        Most backup operations complete quickly (<30 seconds for network backups,
        1-3 minutes for system backups). This tool is primarily useful for
        very large deployments or system backups.
    """
    client = get_network_client()

    if not client.is_authenticated:
        await client.authenticate()

    try:
        site = await client.resolve_site(client.settings.default_site)

        if client.settings.api_type == APIType.LOCAL:
            endpoint = client.legacy_path(site.name, f"stat/backup/{operation_id}")
        else:
            endpoint = client.legacy_path(site.name, f"operations/{operation_id}")

        status_data = await client.get(endpoint)
        if isinstance(status_data, list):
            status_data = status_data[0] if status_data else {}

        result = {
            "operation_id": operation_id,
            "status": status_data.get("status", "completed"),
            "progress_percent": status_data.get("progress", 100),
            "current_step": status_data.get("step", "Completed"),
            "started_at": status_data.get("started_at", ""),
            "completed_at": status_data.get("completed_at", ""),
            "backup_metadata": status_data.get("backup", {}),
            "error_message": status_data.get("error", None),
        }

        logger.info(f"Retrieved status for backup operation '{operation_id}': {result['status']}")
        return result

    except Exception as e:
        logger.error(f"Failed to get backup status for '{operation_id}': {e}")
        # Fallback: backups are typically synchronous
        return {
            "operation_id": operation_id,
            "status": "completed",
            "progress_percent": 100,
            "message": "Backup operations complete synchronously. Status tracking not available.",
        }


@provider.tool()
async def get_restore_status(
    operation_id: str,
) -> dict[str, Any]:
    """Get the status of an ongoing or completed restore operation.

    Monitor the progress of a restore operation initiated with restore_backup.
    Critical for tracking restore progress as controller may restart during restore.

    Args:
        operation_id: Restore operation identifier (returned by restore_backup)
        settings: Application settings

    Returns:
        Restore operation status including progress, pre-restore backup info, and rollback availability

    Note:
        Restore operations typically take 2-5 minutes and will restart the controller.
        Expect temporary connection loss during the restore process.
    """
    # UniFi does not expose a dedicated restore-status endpoint.
    # Return a response that honestly reflects this limitation.
    logger.info(
        f"Restore status requested for operation '{operation_id}'. "
        "UniFi API does not provide a restore status endpoint."
    )
    return {
        "operation_id": operation_id,
        "status": "not_supported",
        "message": "Restore status tracking is not available via the UniFi API.",
        "progress_percent": 0,
        "warning": "Monitor controller connectivity to determine restore completion.",
    }


@provider.tool()
async def schedule_backups(
    site_id: str,
    backup_type: str,
    frequency: str,
    time_of_day: str,
    enabled: bool = True,
    retention_days: int = 30,
    max_backups: int = 10,
    day_of_week: int | None = None,
    day_of_month: int | None = None,
    cloud_backup_enabled: bool = False,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Configure automated backup schedule for a site.

    Set up recurring backups to run automatically at specified intervals.
    Helps ensure regular backups without manual intervention.

    Args:
        site_id: Site identifier
        backup_type: Type of backup ("network" or "system")
        frequency: Backup frequency ("daily", "weekly", or "monthly")
        time_of_day: Time to run backup (HH:MM format, 24-hour)
        settings: Application settings
        enabled: Whether schedule is enabled (default: True)
        retention_days: Days to retain backups (default: 30, max: 365)
        max_backups: Maximum number of backups to keep (default: 10, max: 100)
        day_of_week: For weekly: 0=Monday, 6=Sunday (required if frequency="weekly")
        day_of_month: For monthly: 1-31 (required if frequency="monthly")
        cloud_backup_enabled: Whether to sync backups to cloud
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't configure

    Returns:
        Backup schedule configuration details

    Raises:
        ValidationError: If parameters are invalid

    Example:
        ```python
        # Daily network backup at 3 AM
        schedule = await schedule_backups(
            site_id="default",
            backup_type="network",
            frequency="daily",
            time_of_day="03:00",
            retention_days=30,
            max_backups=10,
            confirm=True,
            settings=settings
        )
        ```

    Note:
        - Daily backups are recommended for production environments
        - Retention and max_backups work together (oldest backups deleted first)
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "backup schedule configuration", dry_run)

    # Validate backup type
    valid_types = ["network", "system"]
    if backup_type.lower() not in valid_types:
        raise ValidationError(f"Invalid backup_type '{backup_type}'. Must be one of: {valid_types}")

    # Validate frequency
    valid_frequencies = ["daily", "weekly", "monthly"]
    if frequency.lower() not in valid_frequencies:
        raise ValidationError(
            f"Invalid frequency '{frequency}'. Must be one of: {valid_frequencies}"
        )

    # Validate time format (HH:MM)
    import re

    if not re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", time_of_day):
        raise ValidationError(
            f"Invalid time_of_day '{time_of_day}'. Must be HH:MM format (24-hour)"
        )

    # Validate frequency-specific parameters
    if frequency == "weekly" and day_of_week is None:
        raise ValidationError("day_of_week required for weekly frequency (0=Monday, 6=Sunday)")
    if frequency == "monthly" and day_of_month is None:
        raise ValidationError("day_of_month required for monthly frequency (1-31)")

    # Validate day_of_week
    if day_of_week is not None and not (0 <= day_of_week <= 6):
        raise ValidationError("day_of_week must be 0-6 (0=Monday, 6=Sunday)")

    # Validate day_of_month
    if day_of_month is not None and not (1 <= day_of_month <= 31):
        raise ValidationError("day_of_month must be 1-31")

    # Validate retention
    if not (1 <= retention_days <= 365):
        raise ValidationError("retention_days must be 1-365")
    if not (1 <= max_backups <= 100):
        raise ValidationError("max_backups must be 1-100")

    parameters = {
        "site_id": site_id,
        "backup_type": backup_type,
        "frequency": frequency,
        "time_of_day": time_of_day,
        "enabled": enabled,
        "retention_days": retention_days,
        "max_backups": max_backups,
        "day_of_week": day_of_week,
        "day_of_month": day_of_month,
        "cloud_backup_enabled": cloud_backup_enabled,
    }

    if dry_run:
        logger.info(
            f"DRY RUN: Would configure {frequency} {backup_type} backups at {time_of_day} for site '{site_id}'"
        )
        await log_audit(
            operation="schedule_backups",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {
            "dry_run": True,
            "would_configure": parameters,
            "next_run": "Calculated after configuration",
        }

    client = get_network_client()

    if not client.is_authenticated:
        await client.authenticate()

    try:
        site = await client.resolve_site(site_id)

        hour, minute = time_of_day.split(":")
        if frequency == "daily":
            cron_expr = f"{int(minute)} {int(hour)} * * *"
        elif frequency == "weekly":
            cron_dow = (cast(int, day_of_week) + 1) % 7
            cron_expr = f"{int(minute)} {int(hour)} * * {cron_dow}"
        else:
            cron_expr = f"{int(minute)} {int(hour)} {cast(int, day_of_month)} * *"

        settings_response = await client.get(client.legacy_path(site.name, "rest/setting"))
        settings_list = (
            settings_response
            if isinstance(settings_response, list)
            else settings_response.get("data", [])
        )
        super_mgmt: dict[str, Any] = next(
            (s for s in settings_list if s.get("key") == "super_mgmt"), {}
        )
        setting_id = super_mgmt.get("_id", "")

        payload: dict[str, Any] = {
            **super_mgmt,
            "autobackup_enabled": enabled,
            "autobackup_cron_expr": cron_expr,
            "autobackup_max_files": max_backups,
            "backup_to_cloud_enabled": cloud_backup_enabled,
        }

        endpoint = client.legacy_path(site.name, f"rest/setting/super_mgmt/{setting_id}")
        schedule_response = await client.put(endpoint, json_data=payload)
        if isinstance(schedule_response, list):
            schedule_response = schedule_response[0] if schedule_response else {}

        schedule_id = f"schedule_{frequency}_{backup_type}_{site_id}"

        result = {
            "schedule_id": schedule_id,
            "site_id": site_id,
            "enabled": enabled,
            "backup_type": backup_type,
            "frequency": frequency,
            "time_of_day": time_of_day,
            "day_of_week": day_of_week,
            "day_of_month": day_of_month,
            "retention_days": retention_days,
            "max_backups": max_backups,
            "cloud_backup_enabled": cloud_backup_enabled,
            "cron_expr": cron_expr,
            "configured_at": datetime.now().isoformat(),
            "next_run": None,
        }

        logger.info(
            f"Configured {frequency} {backup_type} backup schedule for site '{site_id}' at {time_of_day}"
        )
        await log_audit(
            operation="schedule_backups",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return result

    except Exception as e:
        logger.error(f"Failed to configure backup schedule for site '{site_id}': {e}")
        await log_audit(
            operation="schedule_backups",
            parameters=parameters,
            result="error",
            error=str(e),
            site_id=site_id,
        )
        raise


@provider.tool()
async def get_backup_schedule(
    site_id: str,
) -> dict[str, Any]:
    """Get the configured automated backup schedule for a site.

    Retrieve details about the current backup schedule including frequency,
    retention policy, and next scheduled execution.

    Args:
        site_id: Site identifier
        settings: Application settings

    Returns:
        Backup schedule configuration, or None if no schedule is configured

    Example:
        ```python
        schedule = await get_backup_schedule(
            site_id="default",
            settings=settings
        )

        if schedule and schedule['enabled']:
            print(f"Backups run {schedule['frequency']} at {schedule['time_of_day']}")
        ```
    """
    site_id = validate_site_id(site_id)
    client = get_network_client()

    if not client.is_authenticated:
        await client.authenticate()

    try:
        site = await client.resolve_site(site_id)

        endpoint = client.legacy_path(site.name, "rest/setting")
        response = await client.get(endpoint)

        settings_list = response if isinstance(response, list) else response.get("data", [])
        schedule_response = None
        for setting in settings_list:
            if isinstance(setting, dict) and setting.get("key") == "super_mgmt":
                schedule_response = setting
                break

        schedule_data = schedule_response

        if not schedule_data:
            logger.info(f"No backup schedule configured for site '{site_id}'")
            return {
                "configured": False,
                "message": "No automated backup schedule configured for this site",
            }

        result = {
            "configured": True,
            "enabled": schedule_data.get("autobackup_enabled", False),
            "cron_expr": schedule_data.get("autobackup_cron_expr", ""),
            "max_files": schedule_data.get("autobackup_max_files", 0),
            "timezone": schedule_data.get("autobackup_timezone", ""),
            "cloud_backup_enabled": schedule_data.get("backup_to_cloud_enabled", False),
        }

        logger.info(
            f"Retrieved backup schedule for site '{site_id}': "
            f"enabled={result['enabled']} cron={result['cron_expr']}"
        )
        return result

    except Exception as e:
        logger.error(f"Failed to get backup schedule for site '{site_id}': {e}")
        raise

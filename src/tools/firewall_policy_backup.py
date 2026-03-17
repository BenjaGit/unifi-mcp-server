"""Firewall policy backup and restore tools for UniFi v2 API."""

import json
from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..config import APIType, Settings
from ..models.firewall_policy import ConflictStrategy, PolicyBackup
from ..utils import get_logger, log_audit
from ..utils.helpers import get_iso_timestamp
from ..utils.validators import coerce_bool, validate_confirmation, validate_site_id

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = [
    "provider",
    "backup_firewall_policies",
    "restore_firewall_policies",
]

_STRIPPED_FIELDS: frozenset[str] = frozenset(
    {"_id", "site_id", "create_time", "update_time", "origin_id", "origin_type"}
)


def _ensure_local_api(settings: Settings) -> None:
    """Ensure the UniFi controller is accessed via the local API."""

    if settings.api_type != APIType.LOCAL:
        raise NotImplementedError(
            "Firewall policy backup/restore (v2 API) are only available when "
            "UNIFI_API_TYPE='local'. Please configure a local UniFi gateway connection."
        )


def _strip_server_fields(policy: dict[str, Any]) -> dict[str, Any]:
    """Remove server-managed fields from a policy dict."""

    return {k: v for k, v in policy.items() if k not in _STRIPPED_FIELDS}


def _has_zone_or_network_refs(policies: list[dict[str, Any]]) -> bool:
    """Check whether any policy references zone_id or network_ids in source/destination."""

    for policy in policies:
        for direction in ("source", "destination"):
            target = policy.get(direction, {})
            if isinstance(target, dict):
                if target.get("zone_id") or target.get("network_ids"):
                    return True
    return False


@provider.tool()
async def backup_firewall_policies(
    site_id: str,
    output_file: str | None = None,
    include_system: bool | str = False,
) -> dict[str, Any]:
    """Backup all firewall policies from a site to a portable format.

    Exports policies as a JSON envelope that can be restored to the same
    or a different site. Server-managed fields (_id, site_id, timestamps)
    are stripped so that policies can be recreated cleanly.

    Args:
        site_id: Site to export from.
        output_file: Optional file path to write the backup JSON.
        include_system: Include predefined/system policies (default False).

    Returns:
        PolicyBackup envelope as a dict. If output_file is set, also
        includes the file path under the ``output_file`` key.
    """

    validate_site_id(site_id)

    client = get_network_client()
    _ensure_local_api(client.settings)

    include_system_flag = coerce_bool(include_system)

    logger.info(f"Backing up firewall policies for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    endpoint = client.v2_path(site.name, "firewall-policies")
    response = await client.get(endpoint)

    policies_data: list[dict[str, Any]] = (
        response if isinstance(response, list) else response.get("data", [])
    )

    # Filter out system/predefined policies unless requested
    if not include_system_flag:
        policies_data = [p for p in policies_data if not p.get("predefined", False)]

    # Strip server-managed fields
    cleaned = [_strip_server_fields(p) for p in policies_data]

    backup = PolicyBackup(
        exported_at=get_iso_timestamp(),
        source_site=site_id,
        policy_count=len(cleaned),
        policies=cleaned,
    )

    result = backup.model_dump()

    if output_file:
        try:
            with open(output_file, "w") as f:
                json.dump(result, f, indent=2)
            result["output_file"] = output_file
            logger.info(f"Wrote backup to {output_file}")
        except OSError as exc:
            raise ValueError(f"Failed to write backup file: {exc}") from exc

    logger.info(f"Backed up {backup.policy_count} policies from site {site_id}")
    return result


@provider.tool(annotations={"destructiveHint": True})
async def restore_firewall_policies(
    site_id: str,
    policies: list[dict[str, Any]] | None = None,
    input_file: str | None = None,
    conflict_strategy: str = "SKIP",
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Restore firewall policies to a site from a backup or policy list.

    Supports three conflict strategies when a policy with the same name
    already exists on the target site:

    - **SKIP**: leave the existing policy untouched (default).
    - **OVERWRITE**: update the existing policy via PUT.
    - **FAIL**: raise an error immediately.

    Args:
        site_id: Target site to restore into.
        policies: Inline list of policy dicts (mutually exclusive with input_file).
        input_file: Path to a backup JSON file (mutually exclusive with policies).
        conflict_strategy: How to handle name collisions (SKIP/OVERWRITE/FAIL).
        confirm: Must be True to execute (safety gate).
        dry_run: Preview what would happen without making changes.

    Returns:
        Summary dict with created/updated/skipped/failed/total_processed counts.
    """

    validate_site_id(site_id)

    client = get_network_client()
    _ensure_local_api(client.settings)

    dry_run_flag = coerce_bool(dry_run)

    # Validate inputs before confirmation check
    if (policies is None) == (input_file is None):
        raise ValueError("Exactly one of 'policies' or 'input_file' must be provided.")

    # Validate conflict strategy (case-insensitive)
    try:
        strategy = ConflictStrategy(conflict_strategy.upper())
    except ValueError as exc:
        raise ValueError(
            f"Invalid conflict_strategy '{conflict_strategy}'. "
            f"Must be one of: SKIP, OVERWRITE, FAIL."
        ) from exc

    # Confirmation gate
    validate_confirmation(confirm, "restore_firewall_policies", dry_run=dry_run)

    source_site: str | None = None

    # Load from file if needed
    if input_file is not None:
        try:
            with open(input_file) as f:
                backup_data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Failed to read backup file: {exc}") from exc

        if "version" not in backup_data or "policies" not in backup_data:
            raise ValueError(
                "Invalid backup format: missing 'version' or 'policies' key. "
                "Expected a file produced by backup_firewall_policies."
            )

        policies = backup_data["policies"]
        source_site = backup_data.get("source_site")

    assert policies is not None  # guaranteed by earlier validation

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    endpoint = client.v2_path(site.name, "firewall-policies")

    # Fetch existing policies for conflict detection
    existing_response = await client.get(endpoint)
    existing_policies: list[dict[str, Any]] = (
        existing_response
        if isinstance(existing_response, list)
        else existing_response.get("data", [])
    )

    existing_by_name: dict[str, dict[str, Any]] = {
        p["name"]: p for p in existing_policies if "name" in p
    }

    created = 0
    updated = 0
    skipped = 0
    failed = 0

    # Cross-site warning
    warning: str | None = None
    if source_site and source_site != site_id and _has_zone_or_network_refs(policies):
        warning = (
            f"Policies were exported from site '{source_site}' and contain "
            f"zone/network references that may not exist on target site '{site_id}'."
        )

    if dry_run_flag:
        # Simulate without API calls
        for policy in policies:
            name = policy.get("name", "")
            if name in existing_by_name:
                if strategy == ConflictStrategy.SKIP:
                    skipped += 1
                elif strategy == ConflictStrategy.OVERWRITE:
                    updated += 1
                elif strategy == ConflictStrategy.FAIL:
                    raise ValueError(f"Policy '{name}' already exists on site '{site_id}'.")
            else:
                created += 1

        result: dict[str, Any] = {
            "dry_run": True,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
            "total_processed": len(policies),
        }
        if warning:
            result["warning"] = warning
        return result

    # Execute restore
    for policy in policies:
        name = policy.get("name", "")

        if name in existing_by_name:
            if strategy == ConflictStrategy.FAIL:
                raise ValueError(f"Policy '{name}' already exists on site '{site_id}'.")
            elif strategy == ConflictStrategy.SKIP:
                skipped += 1
                continue
            elif strategy == ConflictStrategy.OVERWRITE:
                existing_id = existing_by_name[name].get("_id", "")
                put_endpoint = client.v2_path(site.name, f"firewall-policies/{existing_id}")
                try:
                    await client.put(put_endpoint, json_data=policy)
                    updated += 1
                except Exception as exc:
                    logger.error(f"Failed to update policy '{name}': {exc}")
                    failed += 1
                continue
        else:
            try:
                await client.post(endpoint, json_data=policy)
                created += 1
            except Exception as exc:
                logger.error(f"Failed to create policy '{name}': {exc}")
                failed += 1

    await log_audit(
        operation="restore_firewall_policies",
        parameters={
            "site_id": site_id,
            "conflict_strategy": strategy.value,
            "total": len(policies),
        },
        result="success",
        site_id=site_id,
    )

    logger.info(
        f"Restored policies to site {site_id}: "
        f"{created} created, {updated} updated, {skipped} skipped, {failed} failed"
    )

    result = {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "total_processed": len(policies),
    }
    if warning:
        result["warning"] = warning
    return result

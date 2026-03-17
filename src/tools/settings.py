"""Site settings MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import get_logger, log_audit, validate_confirmation, validate_site_id
from ._helpers import resolve, unwrap

provider = LocalProvider()

__all__ = ["provider", "get_site_settings", "update_site_setting"]


@provider.tool()
async def get_site_settings(
    site_id: str,
    key: str | None = None,
) -> dict[str, Any]:
    """Get site settings (all 37 setting categories or a specific one).

    Settings control site-wide behavior: IPS, DPI, DNS, NTP, management, connectivity, etc.
    Each setting object has a 'key' field identifying its category.

    Args:
        site_id: Site identifier
        settings: Application settings
        key: Optional setting category key to filter (e.g. "ips", "dpi", "connectivity").
            If None, all settings are returned.

    Returns:
        Dictionary with settings list and count
    """
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)

    client, site = await resolve(site_id, get_network_client)
    response = await client.get(client.legacy_path(site.name, "rest/setting"))

    data: list[dict[str, Any]] = unwrap(response)

    if key is not None:
        data = [s for s in data if s.get("key") == key]

    logger.info(
        f"Retrieved {len(data)} settings for site '{site_id}'" + (f" (key={key})" if key else "")
    )
    return {"settings": data, "count": len(data), "site_id": site_id}


@provider.tool(annotations={"destructiveHint": True})
async def update_site_setting(
    site_id: str,
    setting_key: str,
    setting_id: str,
    setting_data: dict[str, Any],
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update a specific site setting category.

    WARNING: Incorrect settings can break network connectivity. Always use get_site_settings
    first to retrieve the current value, then pass the full modified object back.
    The setting_id (_id field) and setting_key (key field) must match what was returned
    by get_site_settings.

    Args:
        site_id: Site identifier
        setting_key: Setting category key (e.g. "ips", "dpi") — from the 'key' field
        setting_id: Setting object ID — from the '_id' field returned by get_site_settings
        setting_data: Complete setting object to PUT (include all fields from GET)
        settings_obj: Application settings
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't update

    Returns:
        Updated setting object
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, f"update site setting '{setting_key}'", dry_run)
    logger = get_logger(__name__)

    parameters = {"site_id": site_id, "setting_key": setting_key, "setting_id": setting_id}

    if dry_run:
        logger.info(f"DRY RUN: Would update site setting '{setting_key}' in site '{site_id}'")
        await log_audit(
            operation="update_site_setting",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_update": setting_key}

    try:
        client, site = await resolve(site_id, get_network_client)
        result = await client.put(
            client.legacy_path(site.name, f"rest/setting/{setting_key}/{setting_id}"),
            json_data=setting_data,
        )
        await log_audit(
            operation="update_site_setting",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )
        return result if isinstance(result, dict) else {"data": result}
    except Exception as e:
        logger.error(f"Failed to update site setting '{setting_key}': {e}")
        await log_audit(
            operation="update_site_setting",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise

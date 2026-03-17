"""WiFi network (SSID) management MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import (
    ResourceNotFoundError,
    ValidationError,
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
    "list_wlans",
    "create_wlan",
    "update_wlan",
    "delete_wlan",
    "get_wlan_statistics",
]


def _map_security_to_integration(security: str, wpa_mode: str = "wpa2") -> str:
    """Map legacy security/wpa_mode to Integration API securityConfiguration type."""
    if security == "open":
        return "OPEN"
    if security == "wpaeap":
        return "WPA2_ENTERPRISE"
    # wpapsk
    mode_map = {"wpa": "WPA_PERSONAL", "wpa2": "WPA2_PERSONAL", "wpa3": "WPA3_PERSONAL"}
    return mode_map.get(wpa_mode, "WPA2_PERSONAL")


def _map_bands_to_integration(wlan_bands: list[str] | None) -> list[float] | None:
    """Map legacy band names to Integration API frequency GHz values."""
    if not wlan_bands:
        return None
    band_map = {"2g": 2.4, "5g": 5, "6g": 6}
    return [band_map[b] for b in wlan_bands if b in band_map]


@provider.tool()
async def list_wlans(
    site_id: str,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    """List all wireless networks (SSIDs) in a site (read-only).

    Args:
        site_id: Site identifier
        limit: Maximum number of WLANs to return
        offset: Number of WLANs to skip

    Returns:
        List of WLAN dictionaries
    """
    site_id = validate_site_id(site_id)
    limit, offset = validate_limit_offset(limit, offset)
    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    response = await client.get(client.integration_path(site.uuid, "wifi/broadcasts"))
    wlans_data: list[dict[str, Any]] = (
        response if isinstance(response, list) else response.get("data", [])
    )

    # Apply pagination
    paginated = wlans_data[offset : offset + limit]

    logger.info(f"Retrieved {len(paginated)} WLANs for site '{site_id}'")
    return paginated


@provider.tool()
async def create_wlan(
    site_id: str,
    name: str,
    security: str,
    password: str | None = None,
    enabled: bool = True,
    is_guest: bool = False,
    wpa_mode: str = "wpa2",
    wpa_enc: str = "ccmp",
    vlan_id: int | None = None,
    networkconf_id: str | None = None,
    ap_group_ids: list[str] | None = None,
    ap_group_mode: str | None = None,
    wlan_bands: list[str] | None = None,
    optimize_iot_wifi_connectivity: bool | None = None,
    minrate_ng_enabled: bool | None = None,
    minrate_ng_data_rate_kbps: int | None = None,
    hide_ssid: bool = False,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create a new wireless network (SSID).

    Args:
        site_id: Site identifier
        name: SSID name
        security: Security type (open, wpapsk, wpaeap)
        password: WiFi password (required for wpapsk)
        enabled: Enable the WLAN immediately
        is_guest: Mark as guest network
        wpa_mode: WPA mode (wpa, wpa2, wpa3)
        wpa_enc: WPA encryption (tkip, ccmp, ccmp-tkip)
        vlan_id: VLAN ID for network isolation
        networkconf_id: Network configuration ID to associate this SSID with
        ap_group_ids: List of AP group IDs to broadcast this SSID on
        ap_group_mode: AP group mode (groups, all). Required when using ap_group_ids.
        wlan_bands: WiFi bands as list (e.g. ["2g"], ["5g"], ["2g", "5g"])
        optimize_iot_wifi_connectivity: Enable IoT WiFi optimizations
        minrate_ng_enabled: Enable minimum data rate for 2.4GHz
        minrate_ng_data_rate_kbps: Minimum 2.4GHz data rate in kbps (e.g. 1000)
        hide_ssid: Hide SSID from broadcast
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't create the WLAN

    Returns:
        Created WLAN dictionary or dry-run result

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ValidationError: If validation fails
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "wifi operation", dry_run)

    # Validate security type
    valid_security = ["open", "wpapsk", "wpaeap"]
    if security not in valid_security:
        raise ValidationError(
            f"Invalid security type '{security}'. Must be one of: {valid_security}"
        )

    # Validate password required for WPA
    if security == "wpapsk" and not password:
        raise ValidationError("Password required for WPA/WPA2/WPA3 security")

    # Validate WPA mode
    valid_wpa_modes = ["wpa", "wpa2", "wpa3"]
    if wpa_mode not in valid_wpa_modes:
        raise ValidationError(f"Invalid WPA mode '{wpa_mode}'. Must be one of: {valid_wpa_modes}")

    # Validate WPA encryption
    valid_wpa_enc = ["tkip", "ccmp", "ccmp-tkip"]
    if wpa_enc not in valid_wpa_enc:
        raise ValidationError(
            f"Invalid WPA encryption '{wpa_enc}'. Must be one of: {valid_wpa_enc}"
        )

    # Build Integration API payload
    wlan_data: dict[str, Any] = {
        "name": name,
        "enabled": enabled,
        "hideName": hide_ssid,
    }

    # Security configuration
    sec_type = _map_security_to_integration(security, wpa_mode)
    sec_config: dict[str, Any] = {"type": sec_type}
    if security == "wpapsk" and password:
        sec_config["passphrase"] = password
    wlan_data["securityConfiguration"] = sec_config

    # Network association
    if networkconf_id:
        wlan_data["network"] = {"type": "SPECIFIC", "networkId": networkconf_id}

    # Broadcasting frequencies
    freq = _map_bands_to_integration(wlan_bands)
    if freq:
        wlan_data["broadcastingFrequenciesGHz"] = freq

    # Log parameters for audit (mask password)
    parameters = {
        "site_id": site_id,
        "name": name,
        "security": security,
        "enabled": enabled,
        "is_guest": is_guest,
        "vlan_id": vlan_id,
        "networkconf_id": networkconf_id,
        "ap_group_ids": ap_group_ids,
        "wlan_bands": wlan_bands,
        "hide_ssid": hide_ssid,
        "password": "***MASKED***" if password else None,
    }

    if dry_run:
        logger.info(f"DRY RUN: Would create WLAN '{name}' in site '{site_id}'")
        await log_audit(
            operation="create_wlan",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        # Don't include passphrase in dry-run output
        safe_data = {k: v for k, v in wlan_data.items() if k != "securityConfiguration"}
        safe_data["securityConfiguration"] = {"type": sec_type}
        return {"dry_run": True, "would_create": safe_data}

    try:
        client = get_network_client()
        if not client.is_authenticated:
            await client.authenticate()

        site = await client.resolve_site(site_id)

        response = await client.post(
            client.integration_path(site.uuid, "wifi/broadcasts"),
            json_data=wlan_data,
        )
        created_wlan = response if isinstance(response, dict) else {}

        logger.info(f"Created WLAN '{name}' in site '{site_id}'")
        await log_audit(
            operation="create_wlan",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return created_wlan

    except Exception as e:
        logger.error(f"Failed to create WLAN '{name}': {e}")
        await log_audit(
            operation="create_wlan",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool()
async def update_wlan(
    site_id: str,
    wlan_id: str,
    name: str | None = None,
    security: str | None = None,
    password: str | None = None,
    enabled: bool | None = None,
    is_guest: bool | None = None,
    wpa_mode: str | None = None,
    wpa_enc: str | None = None,
    vlan_id: int | None = None,
    hide_ssid: bool | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update an existing wireless network.

    Args:
        site_id: Site identifier
        wlan_id: WLAN ID
        name: New SSID name
        security: New security type (open, wpapsk, wpaeap)
        password: New WiFi password
        enabled: Enable/disable the WLAN
        is_guest: Mark as guest network
        wpa_mode: New WPA mode (wpa, wpa2, wpa3)
        wpa_enc: New WPA encryption (tkip, ccmp, ccmp-tkip)
        vlan_id: New VLAN ID
        hide_ssid: Hide/show SSID from broadcast
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't update the WLAN

    Returns:
        Updated WLAN dictionary or dry-run result

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If WLAN not found
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "wifi operation", dry_run)

    # Validate security type if provided
    if security is not None:
        valid_security = ["open", "wpapsk", "wpaeap"]
        if security not in valid_security:
            raise ValidationError(
                f"Invalid security type '{security}'. Must be one of: {valid_security}"
            )

    # Validate WPA mode if provided
    if wpa_mode is not None:
        valid_wpa_modes = ["wpa", "wpa2", "wpa3"]
        if wpa_mode not in valid_wpa_modes:
            raise ValidationError(
                f"Invalid WPA mode '{wpa_mode}'. Must be one of: {valid_wpa_modes}"
            )

    # Validate WPA encryption if provided
    if wpa_enc is not None:
        valid_wpa_enc = ["tkip", "ccmp", "ccmp-tkip"]
        if wpa_enc not in valid_wpa_enc:
            raise ValidationError(
                f"Invalid WPA encryption '{wpa_enc}'. Must be one of: {valid_wpa_enc}"
            )

    # Validate VLAN ID if provided
    if vlan_id is not None and not 1 <= vlan_id <= 4094:
        raise ValidationError(f"Invalid VLAN ID {vlan_id}. Must be between 1 and 4094")

    parameters = {
        "site_id": site_id,
        "wlan_id": wlan_id,
        "name": name,
        "security": security,
        "enabled": enabled,
        "is_guest": is_guest,
        "vlan_id": vlan_id,
        "hide_ssid": hide_ssid,
        "password": "***MASKED***" if password else None,
    }

    if dry_run:
        logger.info(f"DRY RUN: Would update WLAN '{wlan_id}' in site '{site_id}'")
        await log_audit(
            operation="update_wlan",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_update": parameters}

    try:
        client = get_network_client()
        if not client.is_authenticated:
            await client.authenticate()

        site = await client.resolve_site(site_id)

        # Fetch existing WLAN from Integration API
        try:
            existing = await client.get(
                client.integration_path(site.uuid, f"wifi/broadcasts/{wlan_id}")
            )
        except Exception as e:
            if "404" in str(e) or "not found" in str(e).lower():
                raise ResourceNotFoundError("wlan", wlan_id) from e
            raise

        if not existing or not isinstance(existing, dict):
            raise ResourceNotFoundError("wlan", wlan_id)

        # Build update payload from existing + changes
        update_data = existing.copy()

        if name is not None:
            update_data["name"] = name
        if enabled is not None:
            update_data["enabled"] = enabled
        if hide_ssid is not None:
            update_data["hideName"] = hide_ssid

        # Update security configuration
        if security is not None or password is not None or wpa_mode is not None:
            sec_config = update_data.get("securityConfiguration", {}).copy()
            if security is not None:
                sec_config["type"] = _map_security_to_integration(security, wpa_mode or "wpa2")
            if password is not None:
                sec_config["passphrase"] = password
            update_data["securityConfiguration"] = sec_config

        response = await client.put(
            client.integration_path(site.uuid, f"wifi/broadcasts/{wlan_id}"),
            json_data=update_data,
        )
        updated_wlan = response if isinstance(response, dict) else {}

        logger.info(f"Updated WLAN '{wlan_id}' in site '{site_id}'")
        await log_audit(
            operation="update_wlan",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return updated_wlan

    except Exception as e:
        logger.error(f"Failed to update WLAN '{wlan_id}': {e}")
        await log_audit(
            operation="update_wlan",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def delete_wlan(
    site_id: str,
    wlan_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Delete a wireless network.

    Args:
        site_id: Site identifier
        wlan_id: WLAN ID
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't delete the WLAN

    Returns:
        Deletion result dictionary

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If WLAN not found
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "wifi operation", dry_run)

    parameters = {"site_id": site_id, "wlan_id": wlan_id}

    if dry_run:
        logger.info(f"DRY RUN: Would delete WLAN '{wlan_id}' from site '{site_id}'")
        await log_audit(
            operation="delete_wlan",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_delete": wlan_id}

    try:
        client = get_network_client()
        if not client.is_authenticated:
            await client.authenticate()

        site = await client.resolve_site(site_id)

        # Verify WLAN exists before deleting
        try:
            await client.get(client.integration_path(site.uuid, f"wifi/broadcasts/{wlan_id}"))
        except Exception as e:
            if "404" in str(e) or "not found" in str(e).lower():
                raise ResourceNotFoundError("wlan", wlan_id) from e
            raise

        await client.delete(client.integration_path(site.uuid, f"wifi/broadcasts/{wlan_id}"))

        logger.info(f"Deleted WLAN '{wlan_id}' from site '{site_id}'")
        await log_audit(
            operation="delete_wlan",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return {"success": True, "deleted_wlan_id": wlan_id}

    except Exception as e:
        logger.error(f"Failed to delete WLAN '{wlan_id}': {e}")
        await log_audit(
            operation="delete_wlan",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool()
async def get_wlan_statistics(
    site_id: str,
    wlan_id: str | None = None,
) -> dict[str, Any]:
    """Get WiFi usage statistics.

    Args:
        site_id: Site identifier
        wlan_id: Optional WLAN ID to filter statistics

    Returns:
        WLAN statistics dictionary
    """
    site_id = validate_site_id(site_id)
    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    # Get WLANs from Integration API
    wlans_response = await client.get(client.integration_path(site.uuid, "wifi/broadcasts"))
    wlans_data = (
        wlans_response if isinstance(wlans_response, list) else wlans_response.get("data", [])
    )

    # Get active clients (still legacy — no Integration API equivalent)
    clients_response = await client.get(client.legacy_path(site.name, "sta"))
    clients_data = (
        clients_response if isinstance(clients_response, list) else clients_response.get("data", [])
    )

    # Calculate statistics per WLAN
    wlan_stats = []
    for wlan in wlans_data:
        wlan_identifier = wlan.get("id")
        wlan_name = wlan.get("name")

        # Skip if filtering by WLAN ID and this isn't it
        if wlan_id and wlan_identifier != wlan_id:
            continue

        # Count clients on this WLAN by matching ESSID to WLAN name.
        # Clients missing ESSID are excluded to avoid inflating per-SSID stats.
        clients_on_wlan = [c for c in clients_data if c.get("essid") == wlan_name]

        # Calculate total bandwidth
        total_tx = sum(c.get("tx_bytes", 0) for c in clients_on_wlan)
        total_rx = sum(c.get("rx_bytes", 0) for c in clients_on_wlan)

        sec_config = wlan.get("securityConfiguration", {})

        wlan_stats.append(
            {
                "wlan_id": wlan_identifier,
                "name": wlan_name,
                "enabled": wlan.get("enabled", False),
                "security": sec_config.get("type"),
                "client_count": len(clients_on_wlan),
                "total_tx_bytes": total_tx,
                "total_rx_bytes": total_rx,
                "total_bytes": total_tx + total_rx,
            }
        )

    logger.info(f"Retrieved WLAN statistics for site '{site_id}'")

    if wlan_id:
        return wlan_stats[0] if wlan_stats else {}
    return {"site_id": site_id, "wlans": wlan_stats}

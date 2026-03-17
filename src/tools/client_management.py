"""Client management MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import (
    get_logger,
    log_audit,
    sanitize_log_message,
    validate_confirmation,
    validate_mac_address,
    validate_site_id,
)

provider = LocalProvider()

__all__ = [
    "provider",
    "block_client",
    "unblock_client",
    "reconnect_client",
    "authorize_guest",
    "limit_bandwidth",
    "forget_client",
    "unauthorize_guest",
    "list_known_clients",
]


async def _client_action(
    site_id: str,
    client_mac: str,
    action: str,
    operation: str,
    params: dict[str, Any] | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    site_id = validate_site_id(site_id)
    client_mac = validate_mac_address(client_mac)
    validate_confirmation(confirm, "client management operation", dry_run)
    logger = get_logger(__name__)

    details: dict[str, Any] = {"site_id": site_id, "client_mac": client_mac, "action": action}
    if params:
        details.update(params)

    if dry_run:
        logger.info(
            sanitize_log_message(
                f"DRY RUN: Would perform '{action}' for client '{client_mac}' in site '{site_id}'"
            )
        )
        await log_audit(
            operation=operation,
            parameters=details,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "client_mac": client_mac, "action": action, **(params or {})}

    try:
        client = get_network_client()
        if not client.is_authenticated:
            await client.authenticate()

        site = await client.resolve_site(site_id)
        payload: dict[str, Any] = {"action": action}
        if params:
            payload["params"] = params

        await client.post(
            client.integration_path(site.uuid, f"clients/{client_mac}/actions"),
            json_data=payload,
        )
        await log_audit(operation=operation, parameters=details, result="success", site_id=site_id)
        return {"success": True, "client_mac": client_mac, "action": action}
    except Exception as exc:
        logger.error(
            sanitize_log_message(
                f"Failed to perform '{action}' for client '{client_mac}' in site '{site_id}': {exc}"
            )
        )
        await log_audit(operation=operation, parameters=details, result="failed", site_id=site_id)
        raise


@provider.tool()
async def block_client(
    site_id: str,
    client_mac: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Block a client from accessing the network."""
    result = await _client_action(
        site_id=site_id,
        client_mac=client_mac,
        action="block",
        operation="block_client",
        confirm=confirm,
        dry_run=dry_run,
    )
    if result.get("success"):
        result["message"] = "Client blocked from network"
    return result


@provider.tool()
async def unblock_client(
    site_id: str,
    client_mac: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Unblock a previously blocked client."""
    result = await _client_action(
        site_id=site_id,
        client_mac=client_mac,
        action="unblock",
        operation="unblock_client",
        confirm=confirm,
        dry_run=dry_run,
    )
    if result.get("success"):
        result["message"] = "Client unblocked"
    return result


@provider.tool()
async def reconnect_client(
    site_id: str,
    client_mac: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Force a client to reconnect (disconnect and re-authenticate)."""
    result = await _client_action(
        site_id=site_id,
        client_mac=client_mac,
        action="reconnect",
        operation="reconnect_client",
        confirm=confirm,
        dry_run=dry_run,
    )
    if result.get("success"):
        result["message"] = "Client forced to reconnect"
    return result


@provider.tool()
async def authorize_guest(
    site_id: str,
    client_mac: str,
    duration: int,
    upload_limit_kbps: int | None = None,
    download_limit_kbps: int | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Authorize a guest client for network access."""
    params: dict[str, Any] = {"duration": duration}
    if upload_limit_kbps is not None:
        params["uploadLimit"] = upload_limit_kbps
    if download_limit_kbps is not None:
        params["downloadLimit"] = download_limit_kbps

    result = await _client_action(
        site_id=site_id,
        client_mac=client_mac,
        action="authorize-guest",
        operation="authorize_guest",
        params=params,
        confirm=confirm,
        dry_run=dry_run,
    )
    if result.get("success"):
        result["duration"] = duration
        result["message"] = f"Guest authorized for {duration} seconds"
    return result


@provider.tool()
async def limit_bandwidth(
    site_id: str,
    client_mac: str,
    upload_limit_kbps: int | None = None,
    download_limit_kbps: int | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Apply bandwidth restrictions to a client."""
    if upload_limit_kbps is not None and upload_limit_kbps <= 0:
        raise ValueError("Upload limit must be positive")
    if download_limit_kbps is not None and download_limit_kbps <= 0:
        raise ValueError("Download limit must be positive")

    params: dict[str, Any] = {}
    if upload_limit_kbps is not None:
        params["uploadLimit"] = upload_limit_kbps
    if download_limit_kbps is not None:
        params["downloadLimit"] = download_limit_kbps

    result = await _client_action(
        site_id=site_id,
        client_mac=client_mac,
        action="limit-bandwidth",
        operation="limit_bandwidth",
        params=params,
        confirm=confirm,
        dry_run=dry_run,
    )
    if result.get("success"):
        result["upload_limit_kbps"] = upload_limit_kbps
        result["download_limit_kbps"] = download_limit_kbps
        result["message"] = "Bandwidth limits applied"
    return result


@provider.tool(annotations={"destructiveHint": True})
async def forget_client(
    site_id: str,
    client_mac: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Permanently forget a client from the controller history."""
    site_id = validate_site_id(site_id)
    client_mac = validate_mac_address(client_mac)
    validate_confirmation(confirm, "forget client", dry_run)
    logger = get_logger(__name__)
    parameters = {"site_id": site_id, "client_mac": client_mac}

    if dry_run:
        logger.info(
            sanitize_log_message(f"DRY RUN: Would forget client '{client_mac}' in site '{site_id}'")
        )
        await log_audit(
            operation="forget_client",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_forget": client_mac}

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    await client.post(
        client.legacy_path(site.name, "cmd/stamgr"),
        json_data={"cmd": "forget-sta", "macs": [client_mac]},
    )
    await log_audit(
        operation="forget_client", parameters=parameters, result="success", site_id=site_id
    )
    return {"success": True, "client_mac": client_mac, "message": "Client forgotten"}


@provider.tool(annotations={"destructiveHint": True})
async def unauthorize_guest(
    site_id: str,
    client_mac: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Revoke guest network access for a client."""
    site_id = validate_site_id(site_id)
    client_mac = validate_mac_address(client_mac)
    validate_confirmation(confirm, "unauthorize guest", dry_run)
    logger = get_logger(__name__)
    parameters = {"site_id": site_id, "client_mac": client_mac}

    if dry_run:
        logger.info(
            sanitize_log_message(
                f"DRY RUN: Would unauthorize guest '{client_mac}' in site '{site_id}'"
            )
        )
        await log_audit(
            operation="unauthorize_guest",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_unauthorize": client_mac}

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    await client.post(
        client.legacy_path(site.name, "cmd/stamgr"),
        json_data={"cmd": "unauthorize-guest", "mac": client_mac},
    )
    await log_audit(
        operation="unauthorize_guest", parameters=parameters, result="success", site_id=site_id
    )
    return {"success": True, "client_mac": client_mac, "message": "Guest access revoked"}


@provider.tool()
async def list_known_clients(site_id: str, limit: int | None = None) -> dict[str, Any]:
    """List all clients ever seen on the site (historical)."""
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "rest/user"))
    clients_data: list[dict[str, Any]] = (
        response if isinstance(response, list) else response.get("data", [])
    )
    if limit is not None:
        clients_data = clients_data[:limit]

    logger.info(
        sanitize_log_message(f"Listed {len(clients_data)} known clients in site '{site_id}'")
    )
    return {"clients": clients_data, "count": len(clients_data)}

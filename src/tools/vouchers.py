"""Hotspot voucher management tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..models import Voucher
from ..utils import audit_action, get_logger, validate_confirmation

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = [
    "provider",
    "list_vouchers",
    "get_voucher",
    "create_vouchers",
    "delete_voucher",
    "bulk_delete_vouchers",
]


@provider.tool()
async def list_vouchers(
    site_id: str,
    limit: int | None = None,
    offset: int | None = None,
    filter_expr: str | None = None,
) -> list[dict[str, Any]]:
    """List all hotspot vouchers for a site."""
    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    params: dict[str, Any] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    if filter_expr:
        params["filter"] = filter_expr

    logger.info(f"Listing vouchers for site {site_id}")
    response = await client.get(client.legacy_path(site.name, "stat/voucher"), params=params)
    data = response if isinstance(response, list) else response.get("data", [])
    return [Voucher(**voucher).model_dump() for voucher in data]


@provider.tool()
async def get_voucher(site_id: str, voucher_id: str) -> dict[str, Any]:
    """Get details for a specific voucher."""
    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    logger.info(f"Getting voucher {voucher_id} for site {site_id}")
    response = await client.get(client.legacy_path(site.name, "stat/voucher"))
    data = response if isinstance(response, list) else response.get("data", [])
    voucher_data = next((voucher for voucher in data if voucher.get("_id") == voucher_id), None)
    if not voucher_data:
        raise ValueError(f"Voucher {voucher_id} not found")
    return Voucher(**voucher_data).model_dump()


@provider.tool()
async def create_vouchers(
    site_id: str,
    count: int,
    duration: int,
    upload_limit_kbps: int | None = None,
    download_limit_kbps: int | None = None,
    upload_quota_mb: int | None = None,
    download_quota_mb: int | None = None,
    note: str | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create new hotspot vouchers."""
    validate_confirmation(confirm, "create vouchers", dry_run)

    payload: dict[str, Any] = {
        "cmd": "create-voucher",
        "n": count,
        "expire": duration,
        "quota": 0,
    }
    if upload_limit_kbps is not None:
        payload["up"] = upload_limit_kbps
    if download_limit_kbps is not None:
        payload["down"] = download_limit_kbps
    if download_quota_mb is not None:
        payload["bytes"] = download_quota_mb
    elif upload_quota_mb is not None:
        payload["bytes"] = upload_quota_mb
    if note:
        payload["note"] = note

    if dry_run:
        logger.info(f"[DRY RUN] Would create vouchers with payload: {payload}")
        return {"dry_run": True, "payload": payload}

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    logger.info(f"Creating {count} vouchers for site {site_id}")
    response = await client.post(client.legacy_path(site.name, "cmd/hotspot"), json_data=payload)
    data = response if isinstance(response, list) else response.get("data", response)
    if isinstance(data, dict):
        data = [data]

    await audit_action(
        getattr(client, "settings", None),
        action_type="create_vouchers",
        resource_type="voucher",
        resource_id="bulk",
        site_id=site_id,
        details={"count": count, "duration": duration},
    )

    return {"success": True, "count": count, "vouchers": data if isinstance(data, list) else [data]}


@provider.tool(annotations={"destructiveHint": True})
async def delete_voucher(
    site_id: str,
    voucher_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Delete a specific voucher."""
    validate_confirmation(confirm, "delete voucher", dry_run)

    if dry_run:
        logger.info(f"[DRY RUN] Would delete voucher {voucher_id}")
        return {"dry_run": True, "voucher_id": voucher_id}

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    logger.info(f"Deleting voucher {voucher_id} for site {site_id}")
    await client.post(
        client.legacy_path(site.name, "cmd/hotspot"),
        json_data={"cmd": "delete-voucher", "_id": voucher_id},
    )

    await audit_action(
        getattr(client, "settings", None),
        action_type="delete_voucher",
        resource_type="voucher",
        resource_id=voucher_id,
        site_id=site_id,
        details={},
    )

    return {"success": True, "message": f"Voucher {voucher_id} deleted successfully"}


@provider.tool(annotations={"destructiveHint": True})
async def bulk_delete_vouchers(
    site_id: str,
    filter_expr: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Bulk delete vouchers using a filter expression."""
    validate_confirmation(confirm, "bulk delete vouchers", dry_run)

    if dry_run:
        logger.info(f"[DRY RUN] Would bulk delete vouchers with filter: {filter_expr}")
        return {"dry_run": True, "filter": filter_expr}

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    logger.info(f"Bulk deleting vouchers for site {site_id} with filter: {filter_expr}")

    list_response = await client.get(client.legacy_path(site.name, "stat/voucher"))
    all_vouchers = (
        list_response if isinstance(list_response, list) else list_response.get("data", [])
    )

    filtered = all_vouchers
    if filter_expr and "==" in filter_expr:
        field, value = filter_expr.split("==", 1)
        field = field.strip()
        value = value.strip()
        filtered = [voucher for voucher in all_vouchers if str(voucher.get(field, "")) == value]

    deleted_count = 0
    for voucher in filtered:
        voucher_id = voucher.get("_id", "")
        if voucher_id:
            await client.post(
                client.legacy_path(site.name, "cmd/hotspot"),
                json_data={"cmd": "delete-voucher", "_id": voucher_id},
            )
            deleted_count += 1

    await audit_action(
        getattr(client, "settings", None),
        action_type="bulk_delete_vouchers",
        resource_type="voucher",
        resource_id="bulk",
        site_id=site_id,
        details={"filter": filter_expr},
    )

    return {
        "success": True,
        "message": "Vouchers deleted successfully",
        "deleted_count": deleted_count,
    }

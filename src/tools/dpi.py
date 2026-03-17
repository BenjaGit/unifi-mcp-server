"""Deep Packet Inspection (DPI) statistics MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import (
    get_logger,
    sanitize_log_message,
    validate_limit_offset,
    validate_mac_address,
    validate_site_id,
)

provider = LocalProvider()

__all__ = ["provider", "get_dpi_statistics", "list_top_applications", "get_client_dpi"]


@provider.tool()
async def get_dpi_statistics(site_id: str, time_range: str = "24h") -> dict[str, Any]:
    """Get Deep Packet Inspection statistics."""
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)

    valid_ranges = ["1h", "6h", "12h", "24h", "7d", "30d"]
    if time_range not in valid_ranges:
        raise ValueError(f"Invalid time range '{time_range}'. Must be one of: {valid_ranges}")

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "stat/dpi"))
    dpi_data = response if isinstance(response, list) else response.get("data", [])

    app_stats: dict[str, dict[str, Any]] = {}
    category_stats: dict[str, dict[str, Any]] = {}

    for entry in dpi_data:
        app = entry.get("app")
        cat = entry.get("cat")
        tx_bytes = entry.get("tx_bytes", 0)
        rx_bytes = entry.get("rx_bytes", 0)
        total_bytes = tx_bytes + rx_bytes

        if app:
            if app not in app_stats:
                app_stats[app] = {
                    "application": app,
                    "category": cat,
                    "tx_bytes": 0,
                    "rx_bytes": 0,
                    "total_bytes": 0,
                }
            app_stats[app]["tx_bytes"] += tx_bytes
            app_stats[app]["rx_bytes"] += rx_bytes
            app_stats[app]["total_bytes"] += total_bytes

        if cat:
            if cat not in category_stats:
                category_stats[cat] = {
                    "category": cat,
                    "tx_bytes": 0,
                    "rx_bytes": 0,
                    "total_bytes": 0,
                    "application_count": 0,
                }
            category_stats[cat]["tx_bytes"] += tx_bytes
            category_stats[cat]["rx_bytes"] += rx_bytes
            category_stats[cat]["total_bytes"] += total_bytes
            if app:
                category_stats[cat]["application_count"] += 1

    applications = sorted(app_stats.values(), key=lambda x: x["total_bytes"], reverse=True)
    categories = sorted(category_stats.values(), key=lambda x: x["total_bytes"], reverse=True)

    logger.info(
        sanitize_log_message(
            f"Retrieved DPI statistics for site '{site_id}' (time range: {time_range})"
        )
    )

    return {
        "site_id": site_id,
        "time_range": time_range,
        "applications": applications,
        "categories": categories,
        "total_applications": len(applications),
        "total_categories": len(categories),
    }


@provider.tool()
async def list_top_applications(
    site_id: str,
    limit: int = 10,
    time_range: str = "24h",
) -> list[dict[str, Any]]:
    """List top applications by bandwidth usage."""
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)

    dpi_stats = await get_dpi_statistics(site_id, time_range)
    top_apps: list[dict[str, Any]] = dpi_stats["applications"][:limit]

    logger.info(
        sanitize_log_message(
            f"Retrieved top {len(top_apps)} applications for site '{site_id}' (time range: {time_range})"
        )
    )
    return top_apps


@provider.tool()
async def get_client_dpi(
    site_id: str,
    client_mac: str,
    time_range: str = "24h",
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    """Get DPI statistics for a specific client."""
    site_id = validate_site_id(site_id)
    client_mac = validate_mac_address(client_mac)
    limit, offset = validate_limit_offset(limit, offset)
    logger = get_logger(__name__)

    valid_ranges = ["1h", "6h", "12h", "24h", "7d", "30d"]
    if time_range not in valid_ranges:
        raise ValueError(f"Invalid time range '{time_range}'. Must be one of: {valid_ranges}")

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, f"stat/stadpi/{client_mac}"))
    dpi_data = response if isinstance(response, list) else response.get("data", [])

    app_stats: dict[str, dict[str, Any]] = {}
    total_tx = 0
    total_rx = 0

    for entry in dpi_data:
        app = entry.get("app")
        cat = entry.get("cat")
        tx_bytes = entry.get("tx_bytes", 0)
        rx_bytes = entry.get("rx_bytes", 0)
        total_bytes = tx_bytes + rx_bytes

        total_tx += tx_bytes
        total_rx += rx_bytes

        if app:
            if app not in app_stats:
                app_stats[app] = {
                    "application": app,
                    "category": cat,
                    "tx_bytes": 0,
                    "rx_bytes": 0,
                    "total_bytes": 0,
                }
            app_stats[app]["tx_bytes"] += tx_bytes
            app_stats[app]["rx_bytes"] += rx_bytes
            app_stats[app]["total_bytes"] += total_bytes

    applications = sorted(app_stats.values(), key=lambda x: x["total_bytes"], reverse=True)
    paginated_apps = applications[offset : offset + limit]

    total_bytes = total_tx + total_rx
    for app in paginated_apps:
        app["percentage"] = (app["total_bytes"] / total_bytes) * 100 if total_bytes > 0 else 0

    logger.info(
        sanitize_log_message(
            f"Retrieved DPI statistics for client '{client_mac}' in site '{site_id}' (time range: {time_range})"
        )
    )

    return {
        "site_id": site_id,
        "client_mac": client_mac,
        "time_range": time_range,
        "total_tx_bytes": total_tx,
        "total_rx_bytes": total_rx,
        "total_bytes": total_bytes,
        "applications": paginated_apps,
        "total_applications": len(applications),
    }

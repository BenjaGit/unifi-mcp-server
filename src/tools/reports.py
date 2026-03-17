"""Historical reports and session history MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import get_logger, validate_site_id

_VALID_INTERVALS = ("5minutes", "hourly", "daily")
_VALID_REPORT_TYPES = ("site", "user", "ap")

provider = LocalProvider()

__all__ = ["provider", "get_historical_report", "list_sessions"]


@provider.tool()
async def get_historical_report(
    site_id: str,
    interval: str,
    report_type: str,
    start: int,
    end: int,
    attrs: list[str] | None = None,
) -> dict[str, Any]:
    """Get aggregated historical statistics over a time range."""
    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)

    if interval not in _VALID_INTERVALS:
        raise ValueError(
            f"Invalid interval '{interval}'. Must be one of: {', '.join(_VALID_INTERVALS)}"
        )
    if report_type not in _VALID_REPORT_TYPES:
        raise ValueError(
            f"Invalid report_type '{report_type}'. Must be one of: {', '.join(_VALID_REPORT_TYPES)}"
        )

    effective_attrs = attrs or ["bytes", "num_sta", "time"]

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.post(
        client.legacy_path(site.name, f"stat/report/{interval}.{report_type}"),
        json_data={"attrs": effective_attrs, "start": start, "end": end},
    )

    data: list[dict[str, Any]] = (
        response.get("data", []) if isinstance(response, dict) else (response or [])
    )
    logger.info(
        f"Retrieved {len(data)} {interval} {report_type} report records for site '{site_id}'"
    )
    return {
        "data": data,
        "count": len(data),
        "interval": interval,
        "report_type": report_type,
        "site_id": site_id,
    }


@provider.tool()
async def list_sessions(
    site_id: str,
    start: int | None = None,
    end: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """List client session history for a site."""
    import time as _time

    site_id = validate_site_id(site_id)
    logger = get_logger(__name__)

    _now = int(_time.time())
    params: dict[str, Any] = {
        "type": "all",
        "start": start if start is not None else _now - 86400,
        "end": end if end is not None else _now,
    }

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.legacy_path(site.name, "stat/session"), params=params)

    data: list[dict[str, Any]] = (
        response.get("data", []) if isinstance(response, dict) else (response or [])
    )
    if limit is not None:
        data = data[:limit]

    logger.info(f"Retrieved {len(data)} sessions for site '{site_id}'")
    return {"sessions": data, "count": len(data), "site_id": site_id}

"""DPI (Deep Packet Inspection) and country information tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..models import Country, DPIApplication, DPICategory
from ..utils import get_logger

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = ["provider", "list_dpi_categories", "list_dpi_applications", "list_countries"]


@provider.tool()
async def list_dpi_categories() -> list[dict]:
    """List all DPI categories."""
    client = get_network_client()
    logger.info("Listing DPI categories")

    if not client.is_authenticated:
        await client.authenticate()

    response = await client.get(client.integration_base_path("dpi/categories"))
    data = response if isinstance(response, list) else response.get("data", [])
    return [DPICategory(**category).model_dump() for category in data]


@provider.tool()
async def list_dpi_applications(
    limit: int | None = None,
    offset: int | None = None,
    filter_expr: str | None = None,
) -> list[dict]:
    """List all DPI applications."""
    client = get_network_client()
    logger.info("Listing DPI applications")

    if not client.is_authenticated:
        await client.authenticate()

    params: dict[str, Any] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset
    if filter_expr:
        params["filter"] = filter_expr

    response = await client.get(client.integration_base_path("dpi/applications"), params=params)
    data = response if isinstance(response, list) else response.get("data", [])
    return [DPIApplication(**app).model_dump() for app in data]


async def list_countries() -> list[dict]:
    """List all countries for configuration and localization."""
    client = get_network_client()
    logger.info("Listing countries")

    if not client.is_authenticated:
        await client.authenticate()

    response = await client.get(client.integration_base_path("countries"))
    data = response if isinstance(response, list) else response.get("data", [])
    return [Country(**country).model_dump() for country in data]

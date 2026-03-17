"""Reference data MCP tools for supporting resources."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..models.reference_data import Country, DeviceTag
from ..utils import get_logger, validate_limit_offset, validate_site_id

provider = LocalProvider()

__all__ = [
    "provider",
    "list_radius_profiles",
    "list_device_tags",
    "list_countries",
]


async def list_radius_profiles(
    site_id: str,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    """List all RADIUS profiles in a site (read-only)."""
    site_id = validate_site_id(site_id)
    limit, offset = validate_limit_offset(limit, offset)
    logger = get_logger(__name__)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.integration_path(site.uuid, "radius/profiles"))
    profiles_data: list[dict[str, Any]] = (
        response if isinstance(response, list) else response.get("data", [])
    )
    paginated = profiles_data[offset : offset + limit]
    logger.info(f"Retrieved {len(paginated)} RADIUS profiles for site '{site_id}'")
    return paginated


@provider.tool()
async def list_device_tags(
    site_id: str,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    """List all device tags in a site (read-only)."""
    site_id = validate_site_id(site_id)
    limit, offset = validate_limit_offset(limit, offset)
    logger = get_logger(__name__)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.integration_path(site.uuid, "device-tags"))
    tags_data: list[dict[str, Any]] = (
        response if isinstance(response, list) else response.get("data", [])
    )
    paginated = tags_data[offset : offset + limit]
    logger.info(f"Retrieved {len(paginated)} device tags for site '{site_id}'")
    return [DeviceTag(**tag).model_dump() for tag in paginated]


@provider.tool()
async def list_countries(
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    """List all countries with ISO codes (read-only)."""
    limit, offset = validate_limit_offset(limit, offset)
    logger = get_logger(__name__)

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    response = await client.get(client.integration_base_path("countries"))
    countries_data: list[dict[str, Any]] = (
        response if isinstance(response, list) else response.get("data", [])
    )
    paginated = countries_data[offset : offset + limit]
    logger.info(f"Retrieved {len(paginated)} countries")
    return [Country(**country).model_dump() for country in paginated]

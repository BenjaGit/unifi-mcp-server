"""Shared helpers for MCP tool modules."""

from collections.abc import Callable
from typing import Any

from ..api.network_client import NetworkClient, SiteInfo
from ..api.pool import get_network_client
from ..utils import validate_site_id


async def resolve(
    site_id: str,
    client_factory: Callable[[], NetworkClient] | None = None,
) -> tuple[NetworkClient, SiteInfo]:
    """Validate site identifier, ensure auth, and resolve site metadata."""
    resolved_site_id = validate_site_id(site_id)
    factory = client_factory or get_network_client
    client = factory()
    if not client.is_authenticated:
        await client.authenticate()
    site = await client.resolve_site(resolved_site_id)
    return client, site


def unwrap(response: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    """Normalize API responses to a list payload."""
    if isinstance(response, dict):
        data = response.get("data", [])
        return data if isinstance(data, list) else []
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]
    return []

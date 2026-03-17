"""WAN connection management tools."""

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..models import WANConnection
from ..utils import get_logger

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = ["provider", "list_wan_connections"]


@provider.tool()
async def list_wan_connections(site_id: str) -> list[dict]:
    """List all WAN connections for a site."""
    client = get_network_client()
    logger.info(f"Listing WAN connections for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    response = await client.get(client.integration_path(site.uuid, "wans"))
    data = response if isinstance(response, list) else response.get("data", [])
    return [WANConnection(**wan).model_dump() for wan in data]

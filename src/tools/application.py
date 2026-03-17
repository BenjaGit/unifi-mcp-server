"""Application information tools."""

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..utils import get_logger

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = ["provider", "get_application_info"]


@provider.tool()
async def get_application_info() -> dict:
    """Get UniFi Network application information."""
    client = get_network_client()
    logger.info("Fetching application information")

    if not client.is_authenticated:
        await client.authenticate()

    response = await client.get(client.integration_base_path("info"))

    if isinstance(response, dict):
        data = response.get("data", response)
        if isinstance(data, dict):
            return {
                "version": data.get("version"),
                "build": data.get("build"),
                "deployment_type": data.get("deploymentType"),
                "capabilities": data.get("capabilities", []),
                "system_info": data.get("systemInfo", {}),
            }
    return {"raw": response}

"""API client module for UniFi MCP Server.

Three separate API clients for Ubiquiti's three separate APIs:

- NetworkClient: Per-site network configuration (firewall, VLANs, clients, etc.)
  Accessible via local gateway or cloud proxy. Primary client for most tools.

- SiteManagerClient: Cloud-only cross-site management (api.ui.com/v1/).
  ISP metrics, SD-WAN, hosts, multi-site aggregation.

- ProtectClient: Camera/NVR management (not yet implemented).

- UniFiClient: Low-level HTTP client with rate limiting, retries, and error
  handling. Used internally by NetworkClient; not intended for direct use by tools.
"""

from .client import RateLimiter, UniFiClient
from .network_client import NetworkClient, SiteInfo
from .protect_client import ProtectClient
from .site_manager_client import SiteManagerClient

__all__ = [
    "NetworkClient",
    "SiteInfo",
    "SiteManagerClient",
    "ProtectClient",
    "UniFiClient",
    "RateLimiter",
]

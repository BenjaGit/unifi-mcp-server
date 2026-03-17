"""Protect API client stub for future camera/NVR management.

This client will handle the UniFi Protect API for camera and NVR management.
The Protect API is a separate API from the Network API, running on port 443
of the NVR/CloudKey and accessible via the cloud proxy.

Not yet implemented — this stub documents where Protect support will plug in.
"""

from typing import Any

from ..config import Settings
from ..utils import get_logger


class ProtectClient:
    """Client for UniFi Protect API (camera/NVR management).

    NOT YET IMPLEMENTED. This is a placeholder documenting the intended interface.

    The Protect API provides:
    - Camera management (list, configure, reboot)
    - NVR management (storage, settings)
    - Live/recorded video access
    - Motion/smart detection events
    - Viewport management

    Usage (future):
        async with ProtectClient(settings) as client:
            await client.authenticate()
            cameras = await client.list_cameras()
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.logger = get_logger(__name__, settings.log_level)

    async def __aenter__(self) -> "ProtectClient":
        raise NotImplementedError("Protect API client is not yet implemented")

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    async def close(self) -> None:
        """Close the HTTP client."""

    async def authenticate(self) -> None:
        """Authenticate with the Protect API."""
        raise NotImplementedError("Protect API client is not yet implemented")

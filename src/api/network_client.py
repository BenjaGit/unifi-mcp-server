"""Network API client for per-site UniFi Network configuration.

This client builds correct URL paths natively for all three API modes
(CLOUD_V1, CLOUD_EA, LOCAL) without relying on endpoint translation.

Tools use this client instead of UniFiClient directly, calling either
legacy_path() for REST/stat/cmd endpoints or integration_path() for
Integration API v1 endpoints.
"""

from dataclasses import dataclass
from typing import Any

from ..config import APIType, Settings
from ..utils import ResourceNotFoundError, get_logger
from .client import UniFiClient


@dataclass(frozen=True)
class SiteInfo:
    """Resolved site identity with both name and UUID.

    Legacy REST endpoints need the site name (e.g., "default"),
    while Integration API endpoints need the site UUID.
    """

    name: str
    uuid: str


class NetworkClient:
    """Client for UniFi Network API (per-site network configuration).

    Wraps UniFiClient for HTTP transport but builds endpoint paths natively
    for each API mode. No endpoint translation layer needed.

    Usage:
        async with NetworkClient(settings) as client:
            await client.authenticate()
            site = await client.resolve_site(site_id)
            endpoint = client.legacy_path(site.name, "rest/firewallrule")
            response = await client.get(endpoint)
    """

    def __init__(self, settings: Settings) -> None:
        self._client = UniFiClient(settings, api_key=settings.resolved_network_api_key)
        self._settings = settings
        self.logger = get_logger(__name__, settings.log_level)
        self._site_cache: dict[str, SiteInfo] = {}

    async def __aenter__(self) -> "NetworkClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()

    @property
    def is_authenticated(self) -> bool:
        return self._client.is_authenticated

    @property
    def settings(self) -> Settings:
        return self._settings

    async def authenticate(self) -> None:
        """Authenticate with the UniFi API.

        Uses the correct test endpoint for each API mode (unlike the
        base UniFiClient which only knows cloud-format paths).
        """
        from ..utils import AuthenticationError

        try:
            # Use integration_base_path to get the right sites endpoint
            # for any API mode (local, cloud-ea, cloud-v1)
            test_endpoint = self.integration_base_path("sites")
            response = await self._client.get(test_endpoint)

            if isinstance(response, list):
                self._client._authenticated = True
            elif isinstance(response, dict):
                self._client._authenticated = (
                    response.get("meta", {}).get("rc") == "ok"
                    or response.get("data") is not None
                    or response.get("count") is not None
                )
            else:
                self._client._authenticated = False

            self.logger.info(
                f"Successfully authenticated with UniFi Network API "
                f"(response type: {type(response).__name__})"
            )
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            raise AuthenticationError(f"Failed to authenticate with UniFi Network API: {e}") from e

    # ── Path builders ──────────────────────────────────────────────

    # Cloud EA and local use different endpoint names for the same resources.
    # Tools use cloud-format names; this mapping translates for local.
    _LOCAL_ENDPOINT_MAP: dict[str, str] = {
        "sta": "stat/sta",
        "devices": "stat/device",
    }

    def legacy_path(self, site_name: str, endpoint: str) -> str:
        """Build a legacy REST/stat/cmd endpoint path.

        Args:
            site_name: Site name (e.g., "default"). Use SiteInfo.name.
            endpoint: Path after the site prefix (e.g., "rest/firewallrule",
                      "stat/device", "cmd/backup"). Uses cloud-format names —
                      local-specific mappings (e.g., "sta" → "stat/sta") are
                      applied automatically.

        Returns:
            Local:    /proxy/network/api/s/{site_name}/{endpoint}
            Cloud EA: /ea/sites/{site_name}/{endpoint}
            Cloud V1: /v1/{endpoint}
        """
        endpoint = endpoint.lstrip("/")

        if self._settings.api_type == APIType.LOCAL:
            endpoint = self._LOCAL_ENDPOINT_MAP.get(endpoint, endpoint)
            return f"/proxy/network/api/s/{site_name}/{endpoint}"
        elif self._settings.api_type == APIType.CLOUD_EA:
            return f"/ea/sites/{site_name}/{endpoint}"
        else:  # CLOUD_V1
            return f"/v1/{endpoint}"

    def integration_path(self, site_uuid: str, endpoint: str) -> str:
        """Build an Integration API v1 endpoint path.

        Args:
            site_uuid: Site UUID. Use SiteInfo.uuid.
            endpoint: Path after sites/{uuid}/ (e.g., "firewall/zones",
                      "networks", "clients").

        Returns:
            Local:    /proxy/network/integration/v1/sites/{site_uuid}/{endpoint}
            Cloud EA: /integration/v1/sites/{site_uuid}/{endpoint}
            Cloud V1: /v1/sites/{site_uuid}/{endpoint}
        """
        endpoint = endpoint.lstrip("/")

        if self._settings.api_type == APIType.LOCAL:
            return f"/proxy/network/integration/v1/sites/{site_uuid}/{endpoint}"
        elif self._settings.api_type == APIType.CLOUD_EA:
            return f"/integration/v1/sites/{site_uuid}/{endpoint}"
        else:  # CLOUD_V1
            return f"/v1/sites/{site_uuid}/{endpoint}"

    def integration_base_path(self, endpoint: str) -> str:
        """Build an Integration API v1 path without site prefix.

        Used for site-level endpoints like listing sites.

        Args:
            endpoint: Path (e.g., "sites").

        Returns:
            Local:    /proxy/network/integration/v1/{endpoint}
            Cloud EA: /integration/v1/{endpoint}
            Cloud V1: /v1/{endpoint}
        """
        endpoint = endpoint.lstrip("/")

        if self._settings.api_type == APIType.LOCAL:
            return f"/proxy/network/integration/v1/{endpoint}"
        elif self._settings.api_type == APIType.CLOUD_EA:
            return f"/integration/v1/{endpoint}"
        else:  # CLOUD_V1
            return f"/v1/{endpoint}"

    def v2_path(self, site_name: str, endpoint: str) -> str:
        """Build a v2 API path (local gateway only).

        Args:
            site_name: Site name (e.g., "default").
            endpoint: Path after the site prefix (e.g., "firewall/policies").

        Returns:
            /proxy/network/v2/api/site/{site_name}/{endpoint}

        Raises:
            NotImplementedError: If api_type is not LOCAL.
        """
        if self._settings.api_type != APIType.LOCAL:
            raise NotImplementedError(
                "v2 API is only available with local gateway access. "
                "Set UNIFI_API_TYPE=local and configure UNIFI_LOCAL_HOST."
            )
        endpoint = endpoint.lstrip("/")
        return f"/proxy/network/v2/api/site/{site_name}/{endpoint}"

    # ── Site resolution ────────────────────────────────────────────

    async def resolve_site(self, site_identifier: str | None = None) -> SiteInfo:
        """Resolve a user-provided site identifier to SiteInfo with both name and UUID.

        Args:
            site_identifier: Friendly name, UUID, or None for default site.

        Returns:
            SiteInfo with both name and uuid populated.

        Raises:
            ResourceNotFoundError: If the site cannot be found.
        """
        if not site_identifier:
            site_identifier = self._settings.default_site

        # Check cache
        cached = self._site_cache.get(site_identifier)
        if cached:
            return cached

        # For cloud EA, if the identifier looks like a UUID, we can use it directly
        # but we still need to resolve the name for legacy paths
        sites_endpoint = self.integration_base_path("sites")
        response = await self._client.get(sites_endpoint)

        # Handle both list and dict responses
        if isinstance(response, list):
            sites = response
        else:
            sites = response.get("data", response.get("sites", []))

        for site in sites:
            site_uuid = site.get("id") or site.get("_id") or ""
            site_name = site.get("internalReference") or site.get("name") or ""
            short_name = site.get("shortName") or ""

            if not site_uuid:
                continue

            identifiers = {v for v in (site_uuid, site_name, short_name) if v}

            if site_identifier in identifiers:
                info = SiteInfo(name=site_name or site_uuid, uuid=site_uuid)
                # Cache by all known identifiers
                for ident in identifiers:
                    self._site_cache[ident] = info
                return info

        raise ResourceNotFoundError("site", site_identifier)

    # ── HTTP methods (delegate to UniFiClient) ─────────────────────

    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Make a GET request."""
        return await self._client.get(endpoint, params=params)

    async def post(
        self,
        endpoint: str,
        json_data: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Make a POST request."""
        return await self._client.post(endpoint, json_data=json_data, params=params)

    async def put(
        self,
        endpoint: str,
        json_data: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Make a PUT request."""
        return await self._client.put(endpoint, json_data=json_data, params=params)

    async def delete(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Make a DELETE request."""
        return await self._client.delete(endpoint, params=params)

    async def raw_request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> Any:
        """Make a raw HTTP request via the underlying httpx client.

        Used for non-JSON operations like binary downloads.
        """
        full_url = f"{self._settings.base_url}{endpoint}"
        response = await self._client.client.request(method, full_url, **kwargs)
        response.raise_for_status()
        return response

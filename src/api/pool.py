"""Long-lived UniFi API client pool."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Final

from ..config import Settings
from .network_client import NetworkClient
from .site_manager_client import SiteManagerClient

_network_client: NetworkClient | None = None
_site_manager_client: SiteManagerClient | None = None
_is_initialized: bool = False


async def initialize(settings: Settings) -> None:
    """Initialize pooled clients (idempotent)."""

    global _network_client, _site_manager_client, _is_initialized

    if _is_initialized:
        return

    network_client: NetworkClient | None = None
    site_manager_client: SiteManagerClient | None = None

    try:
        network_client = NetworkClient(settings)
        await network_client.__aenter__()
        await network_client.authenticate()

        if settings.site_manager_enabled and settings.resolved_site_manager_api_key:
            site_manager_client = SiteManagerClient(settings)
            await site_manager_client.__aenter__()

        _network_client = network_client
        _site_manager_client = site_manager_client
        _is_initialized = True
    except Exception:
        if network_client is not None:
            await network_client.close()
        if site_manager_client is not None:
            await site_manager_client.close()
        raise


async def shutdown() -> None:
    """Close pooled clients and reset state."""

    global _network_client, _site_manager_client, _is_initialized

    if _network_client is not None:
        await _network_client.close()
        _network_client = None

    if _site_manager_client is not None:
        await _site_manager_client.close()
        _site_manager_client = None

    _is_initialized = False


def get_network_client() -> NetworkClient:
    """Return the pooled NetworkClient instance."""

    if _network_client is None:
        raise RuntimeError("Network client pool not initialized. Call pool.initialize() first.")
    return _network_client


def get_site_manager_client() -> SiteManagerClient:
    """Return the pooled SiteManagerClient instance."""

    if _site_manager_client is None:
        raise RuntimeError(
            "Site Manager client not initialized. Enable Site Manager credentials or "
            "call pool.initialize() with site_manager_enabled=True."
        )
    return _site_manager_client


def is_initialized() -> bool:
    """Return True when the pool has been initialized."""

    return _is_initialized


@asynccontextmanager
async def network_client(
    settings: Settings,
    factory: Callable[[Settings], NetworkClient] | type[NetworkClient] | None = None,
) -> AsyncIterator[NetworkClient]:
    """Yield a pooled NetworkClient when available, otherwise create one."""

    if is_initialized():
        yield get_network_client()
        return

    client_factory = factory or NetworkClient
    async with client_factory(settings) as client:
        await client.authenticate()
        yield client


__all__: Final = [
    "initialize",
    "shutdown",
    "get_network_client",
    "get_site_manager_client",
    "is_initialized",
    "network_client",
]

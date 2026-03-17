"""Tests for src/api/pool."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api import pool
from src.config import Settings


@dataclass
class FakeSettings:
    site_manager_enabled: bool = False
    resolved_site_manager_api_key: str | None = None


def make_settings(**overrides: Any) -> Settings:
    return cast(Settings, FakeSettings(**overrides))


@pytest.fixture(autouse=True)
async def reset_pool() -> Any:
    """Ensure global pool state is clean between tests."""

    await pool.shutdown()
    yield
    await pool.shutdown()


def _setup_network_client(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    instance = MagicMock()
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)
    instance.authenticate = AsyncMock()
    instance.close = AsyncMock()
    monkeypatch.setattr(pool, "NetworkClient", MagicMock(return_value=instance))
    return instance


def _setup_site_manager_client(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    instance = MagicMock()
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=None)
    instance.close = AsyncMock()
    monkeypatch.setattr(pool, "SiteManagerClient", MagicMock(return_value=instance))
    return instance


def test_get_network_client_requires_initialization() -> None:
    with pytest.raises(RuntimeError):
        pool.get_network_client()


@pytest.mark.anyio
async def test_initialize_creates_network_client(monkeypatch: pytest.MonkeyPatch) -> None:
    network_instance = _setup_network_client(monkeypatch)

    await pool.initialize(make_settings())

    network_instance.__aenter__.assert_awaited_once()
    network_instance.authenticate.assert_awaited_once()
    assert pool.get_network_client() is network_instance
    assert pool.is_initialized()


@pytest.mark.anyio
async def test_site_manager_client_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_network_client(monkeypatch)
    settings = make_settings(site_manager_enabled=True, resolved_site_manager_api_key="abc123")
    site_manager_instance = _setup_site_manager_client(monkeypatch)

    await pool.initialize(settings)

    assert pool.get_site_manager_client() is site_manager_instance
    site_manager_instance.__aenter__.assert_awaited_once()


@pytest.mark.anyio
async def test_get_site_manager_client_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _setup_network_client(monkeypatch)
    await pool.initialize(make_settings())

    with pytest.raises(RuntimeError):
        pool.get_site_manager_client()


@pytest.mark.anyio
async def test_shutdown_resets_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    network_instance = _setup_network_client(monkeypatch)
    site_manager_instance = _setup_site_manager_client(monkeypatch)
    settings = make_settings(site_manager_enabled=True, resolved_site_manager_api_key="token")

    await pool.initialize(settings)
    await pool.shutdown()

    network_instance.close.assert_awaited_once()
    site_manager_instance.close.assert_awaited_once()
    assert not pool.is_initialized()
    with pytest.raises(RuntimeError):
        pool.get_network_client()


@pytest.mark.anyio
async def test_network_client_uses_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    network_instance = _setup_network_client(monkeypatch)
    await pool.initialize(make_settings())
    network_factory = cast(MagicMock, pool.NetworkClient)
    network_factory.reset_mock()

    async with pool.network_client(make_settings(), pool.NetworkClient) as client:
        assert client is network_instance

    network_factory.assert_not_called()


@pytest.mark.anyio
async def test_network_client_factory_creates_client(monkeypatch: pytest.MonkeyPatch) -> None:
    factory_instance = MagicMock()
    factory_instance.__aenter__ = AsyncMock(return_value=factory_instance)
    factory_instance.__aexit__ = AsyncMock(return_value=None)
    factory_instance.authenticate = AsyncMock()

    factory = MagicMock(return_value=factory_instance)

    async with pool.network_client(make_settings(), factory) as client:
        assert client is factory_instance

    factory.assert_called_once()
    factory_instance.__aenter__.assert_awaited_once()
    factory_instance.authenticate.assert_awaited_once()
    factory_instance.__aexit__.assert_awaited_once()

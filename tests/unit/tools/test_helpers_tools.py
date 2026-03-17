"""Tests for shared tool helper utilities."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_resolve_validates_authenticates_and_resolves_site() -> None:
    """resolve() validates site_id and resolves through pooled client."""
    from src.tools._helpers import resolve

    mock_site = MagicMock(name="default", uuid="site-uuid")
    mock_client = MagicMock()
    mock_client.is_authenticated = False
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=mock_site)

    with patch("src.tools._helpers.get_network_client", return_value=mock_client):
        client, site = await resolve("default")

    assert client is mock_client
    assert site is mock_site
    mock_client.authenticate.assert_awaited_once()
    mock_client.resolve_site.assert_awaited_once_with("default")


def test_unwrap_handles_dict_and_list_shapes() -> None:
    """unwrap() returns list payloads from dict or list responses."""
    from src.tools._helpers import unwrap

    list_payload = [{"id": 1}, {"id": 2}]
    assert unwrap({"data": list_payload}) == list_payload
    assert unwrap(list_payload) == list_payload
    assert unwrap({"data": {"id": 1}}) == []
    assert unwrap({}) == []

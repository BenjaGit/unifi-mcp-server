"""Tests for DNS policy tools using pooled clients."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.utils import ValidationError


def make_client() -> AsyncMock:
    client = AsyncMock()
    client.settings = SimpleNamespace()
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(
        return_value=SimpleNamespace(name="default", uuid="uuid-default")
    )
    client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.put = AsyncMock()
    client.delete = AsyncMock()
    return client


@pytest.fixture
def dns_client():
    client = make_client()
    with patch("src.tools.dns_policies.get_network_client", return_value=client):
        yield client


@pytest.fixture
def sample_policies():
    return [
        {
            "id": "policy-1",
            "type": "A_RECORD",
            "domain": "api.local",
            "enabled": True,
            "ipv4Address": "127.0.0.1",
            "ttlSeconds": 0,
        },
        {
            "id": "policy-2",
            "type": "CNAME",
            "domain": "alias.local",
            "target": "real.local",
            "ttlSeconds": 300,
        },
    ]


class TestListDNSPolicies:
    @pytest.mark.asyncio
    async def test_success(self, dns_client, sample_policies):
        from src.tools.dns_policies import list_dns_policies

        dns_client.get.return_value = sample_policies

        result = await list_dns_policies("default")

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_pagination_params(self, dns_client):
        from src.tools.dns_policies import list_dns_policies

        dns_client.get.return_value = []

        await list_dns_policies("default", limit=5, offset=2)

        _, kwargs = dns_client.get.call_args
        assert kwargs["params"]["limit"] == 5
        assert kwargs["params"]["offset"] == 2


class TestGetDNSPolicy:
    @pytest.mark.asyncio
    async def test_wrapped_response(self, dns_client, sample_policies):
        from src.tools.dns_policies import get_dns_policy

        dns_client.get.return_value = {"data": sample_policies[0]}

        result = await get_dns_policy("default", "policy-1")

        assert result["domain"] == "api.local"


class TestCreateDNSPolicy:
    @pytest.mark.asyncio
    async def test_success(self, dns_client):
        from src.tools.dns_policies import create_dns_policy

        dns_client.post.return_value = {"data": {"id": "policy-3", "domain": "demo"}}

        with patch("src.tools.dns_policies.audit_action", new_callable=AsyncMock) as mock_audit:
            result = await create_dns_policy("default", "A_RECORD", "demo", confirm=True)

        assert result["domain"] == "demo"
        mock_audit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dry_run(self, dns_client):
        from src.tools.dns_policies import create_dns_policy

        result = await create_dns_policy("default", "A_RECORD", "demo", dry_run=True, confirm=True)

        assert result["dry_run"] is True
        dns_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_requires_confirm(self, dns_client):
        from src.tools.dns_policies import create_dns_policy

        with pytest.raises(ValidationError):
            await create_dns_policy("default", "A_RECORD", "demo", confirm=False)


class TestUpdateDNSPolicy:
    @pytest.mark.asyncio
    async def test_success(self, dns_client):
        from src.tools.dns_policies import update_dns_policy

        dns_client.put.return_value = {"data": {"id": "policy-1", "enabled": False}}

        with patch("src.tools.dns_policies.audit_action", new_callable=AsyncMock) as mock_audit:
            result = await update_dns_policy("default", "policy-1", enabled=False, confirm=True)

        assert result["enabled"] is False
        mock_audit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dry_run(self, dns_client):
        from src.tools.dns_policies import update_dns_policy

        result = await update_dns_policy(
            "default", "policy-1", domain="demo", dry_run=True, confirm=True
        )

        assert result["dry_run"] is True
        dns_client.put.assert_not_called()


class TestDeleteDNSPolicy:
    @pytest.mark.asyncio
    async def test_success(self, dns_client):
        from src.tools.dns_policies import delete_dns_policy

        with patch("src.tools.dns_policies.audit_action", new_callable=AsyncMock) as mock_audit:
            result = await delete_dns_policy("default", "policy-1", confirm=True)

        assert result["success"] is True
        mock_audit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dry_run(self, dns_client):
        from src.tools.dns_policies import delete_dns_policy

        result = await delete_dns_policy("default", "policy-1", dry_run=True, confirm=True)

        assert result["dry_run"] is True

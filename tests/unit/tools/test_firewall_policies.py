"""Unit tests for firewall policy tools using pooled clients."""

import asyncio
from collections.abc import Generator
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Provide a lightweight fastmcp stub when the dependency is unavailable.
try:  # pragma: no cover - executed only when fastmcp is missing
    import fastmcp  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover
    import sys

    providers_module = ModuleType("fastmcp.server.providers")

    class LocalProvider:
        def tool(self, *_args, **_kwargs):
            def decorator(func):
                return func

            return decorator

    providers_module.LocalProvider = LocalProvider  # type: ignore[attr-defined]

    server_module = ModuleType("fastmcp.server")
    server_module.providers = providers_module  # type: ignore[attr-defined]

    fastmcp_module = ModuleType("fastmcp")
    fastmcp_module.server = server_module  # type: ignore[attr-defined]

    sys.modules.setdefault("fastmcp", fastmcp_module)
    sys.modules.setdefault("fastmcp.server", server_module)
    sys.modules.setdefault("fastmcp.server.providers", providers_module)

from src.config.config import APIType
from src.utils.exceptions import APIError, ResourceNotFoundError


def run(coro):
    """Execute an async coroutine synchronously for tests."""

    return asyncio.run(coro)


def make_mock_client(
    *,
    api_type: APIType = APIType.LOCAL,
    site_name: str = "default",
    site_uuid: str = "uuid-default",
) -> AsyncMock:
    """Create a reusable mock NetworkClient instance."""

    client = AsyncMock()
    client.settings = SimpleNamespace(api_type=api_type)
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(return_value=SimpleNamespace(name=site_name, uuid=site_uuid))
    client.v2_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/v2/api/site/{site}/{ep}"
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
def firewall_client() -> Generator[AsyncMock, None, None]:
    """Provide a patched pooled client for firewall policy tools."""

    client = make_mock_client()
    with patch("src.tools.firewall_policies.get_network_client", return_value=client):
        yield client


@pytest.fixture
def sample_policy() -> dict:
    """Sample firewall policy returned by the UniFi API."""

    return {
        "_id": "policy-id",
        "name": "Block IOT",
        "enabled": True,
        "action": "BLOCK",
        "predefined": False,
        "index": 10,
        "protocol": "all",
        "ip_version": "BOTH",
        "connection_state_type": "CUSTOM",
        "connection_states": ["NEW"],
        "source": {"zone_id": "zone-a", "matching_target": "NETWORK"},
        "destination": {"zone_id": "zone-b", "matching_target": "NETWORK"},
    }


@pytest.fixture
def sample_policy_response(sample_policy: dict) -> list[dict]:
    """List response containing multiple firewall policies."""

    allow_policy = sample_policy.copy()
    allow_policy.update({"_id": "allow-policy", "action": "ALLOW", "predefined": True})
    return [sample_policy, allow_policy]


class TestListFirewallPolicies:
    """Tests for list_firewall_policies tool."""

    def test_success(self, firewall_client: AsyncMock, sample_policy_response: list[dict]) -> None:
        from src.tools.firewall_policies import list_firewall_policies

        firewall_client.get.return_value = sample_policy_response

        result = run(list_firewall_policies("default"))

        assert len(result) == 2
        assert result[0]["id"] == "policy-id"

    def test_empty_response(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import list_firewall_policies

        firewall_client.get.return_value = []

        result = run(list_firewall_policies("default"))

        assert result == []

    def test_cloud_api_rejected(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import list_firewall_policies

        firewall_client.settings.api_type = APIType.CLOUD_EA

        with pytest.raises(NotImplementedError):
            run(list_firewall_policies("default"))

    def test_api_error_propagates(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import list_firewall_policies

        firewall_client.get.side_effect = APIError("boom")

        with pytest.raises(APIError):
            run(list_firewall_policies("default"))

    def test_custom_site_id(
        self, firewall_client: AsyncMock, sample_policy_response: list[dict]
    ) -> None:
        from src.tools.firewall_policies import list_firewall_policies

        firewall_client.resolve_site.return_value = SimpleNamespace(
            name="custom", uuid="uuid-custom"
        )
        firewall_client.get.return_value = sample_policy_response

        run(list_firewall_policies("custom"))

        called_endpoint = firewall_client.get.call_args[0][0]
        assert "custom" in called_endpoint

    def test_authenticates_when_needed(
        self, firewall_client: AsyncMock, sample_policy_response: list[dict]
    ) -> None:
        from src.tools.firewall_policies import list_firewall_policies

        firewall_client.is_authenticated = False
        firewall_client.get.return_value = sample_policy_response

        run(list_firewall_policies("default"))

        firewall_client.authenticate.assert_awaited_once()


class TestGetFirewallPolicy:
    """Tests for get_firewall_policy tool."""

    def test_success(self, firewall_client: AsyncMock, sample_policy: dict) -> None:
        from src.tools.firewall_policies import get_firewall_policy

        firewall_client.get.return_value = sample_policy

        result = run(get_firewall_policy("policy-id", "default"))

        assert result["id"] == "policy-id"

    def test_wrapped_response(self, firewall_client: AsyncMock, sample_policy: dict) -> None:
        from src.tools.firewall_policies import get_firewall_policy

        firewall_client.get.return_value = {"data": sample_policy}

        result = run(get_firewall_policy("policy-id", "default"))

        assert result["name"] == "Block IOT"

    def test_not_found(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import get_firewall_policy

        firewall_client.get.side_effect = ResourceNotFoundError("firewall_policy", "missing")

        with pytest.raises(ResourceNotFoundError):
            run(get_firewall_policy("missing", "default"))

    def test_cloud_api_rejected(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import get_firewall_policy

        firewall_client.settings.api_type = APIType.CLOUD_EA

        with pytest.raises(NotImplementedError):
            run(get_firewall_policy("policy-id", "default"))

    def test_empty_response_raises(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import get_firewall_policy

        firewall_client.get.return_value = {}

        with pytest.raises(ResourceNotFoundError):
            run(get_firewall_policy("policy-id", "default"))


class TestCreateFirewallPolicy:
    """Tests for create_firewall_policy tool."""

    def test_success(self, firewall_client: AsyncMock, sample_policy: dict) -> None:
        from src.tools.firewall_policies import create_firewall_policy

        firewall_client.post.return_value = sample_policy

        result = run(
            create_firewall_policy(
                name="Block IOT",
                action="BLOCK",
                site_id="default",
                confirm=True,
            )
        )

        assert result["id"] == "policy-id"
        firewall_client.post.assert_awaited_once()

    def test_dry_run(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import create_firewall_policy

        result = run(
            create_firewall_policy(
                name="Block IOT",
                action="BLOCK",
                site_id="default",
                dry_run=True,
            )
        )

        assert result["status"] == "dry_run"
        firewall_client.post.assert_not_called()

    def test_missing_confirm_raises(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import create_firewall_policy

        with pytest.raises(ValueError):
            run(
                create_firewall_policy(
                    name="Block IOT",
                    action="BLOCK",
                    site_id="default",
                    confirm=False,
                )
            )

    def test_invalid_action(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import create_firewall_policy

        with pytest.raises(ValueError):
            run(
                create_firewall_policy(
                    name="Block IOT",
                    action="DENY",
                    site_id="default",
                    confirm=True,
                )
            )

    def test_cloud_api_rejected(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import create_firewall_policy

        firewall_client.settings.api_type = APIType.CLOUD_EA

        with pytest.raises(NotImplementedError):
            run(
                create_firewall_policy(
                    name="Block IOT",
                    action="BLOCK",
                    site_id="default",
                    confirm=True,
                )
            )


class TestUpdateFirewallPolicy:
    """Tests for update_firewall_policy tool."""

    def test_success(self, firewall_client: AsyncMock, sample_policy: dict) -> None:
        from src.tools.firewall_policies import update_firewall_policy

        updated_policy = sample_policy.copy()
        updated_policy["name"] = "Updated"
        firewall_client.put.return_value = updated_policy

        result = run(
            update_firewall_policy(
                policy_id="policy-id",
                site_id="default",
                name="Updated",
                confirm=True,
            )
        )

        assert result["name"] == "Updated"

    def test_dry_run(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import update_firewall_policy

        result = run(
            update_firewall_policy(
                policy_id="policy-id",
                site_id="default",
                name="Updated",
                dry_run=True,
            )
        )

        assert result["status"] == "dry_run"
        firewall_client.put.assert_not_called()

    def test_missing_confirm_raises(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import update_firewall_policy

        with pytest.raises(ValueError):
            run(
                update_firewall_policy(
                    policy_id="policy-id",
                    site_id="default",
                    name="Updated",
                    confirm=False,
                )
            )

    def test_not_found(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import update_firewall_policy

        firewall_client.put.side_effect = ResourceNotFoundError("firewall_policy", "missing")

        with pytest.raises(ResourceNotFoundError):
            run(
                update_firewall_policy(
                    policy_id="missing",
                    site_id="default",
                    name="Updated",
                    confirm=True,
                )
            )


class TestDeleteFirewallPolicy:
    """Tests for delete_firewall_policy tool."""

    def test_success(self, firewall_client: AsyncMock, sample_policy: dict) -> None:
        from src.tools.firewall_policies import delete_firewall_policy

        firewall_client.get.return_value = sample_policy

        result = run(
            delete_firewall_policy(
                policy_id="policy-id",
                site_id="default",
                confirm=True,
            )
        )

        assert result["status"] == "success"
        firewall_client.delete.assert_awaited_once()

    def test_dry_run(self, firewall_client: AsyncMock, sample_policy: dict) -> None:
        from src.tools.firewall_policies import delete_firewall_policy

        firewall_client.get.return_value = sample_policy

        result = run(
            delete_firewall_policy(
                policy_id="policy-id",
                site_id="default",
                dry_run=True,
            )
        )

        assert result["status"] == "dry_run"
        firewall_client.delete.assert_not_called()

    def test_missing_confirm_raises(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import delete_firewall_policy

        with pytest.raises(ValueError):
            run(
                delete_firewall_policy(
                    policy_id="policy-id",
                    site_id="default",
                    confirm=False,
                )
            )

    def test_predefined_policy_rejected(
        self, firewall_client: AsyncMock, sample_policy: dict
    ) -> None:
        from src.tools.firewall_policies import delete_firewall_policy

        sample_policy["predefined"] = True
        firewall_client.get.return_value = sample_policy

        with pytest.raises(ValueError):
            run(
                delete_firewall_policy(
                    policy_id="policy-id",
                    site_id="default",
                    confirm=True,
                )
            )

    def test_not_found(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import delete_firewall_policy

        firewall_client.get.side_effect = ResourceNotFoundError("firewall_policy", "missing")

        with pytest.raises(ResourceNotFoundError):
            run(
                delete_firewall_policy(
                    policy_id="missing",
                    site_id="default",
                    confirm=True,
                )
            )


class TestFirewallPolicyOrdering:
    """Tests for ordering helpers."""

    def test_get_ordering_success(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import get_firewall_policy_ordering

        firewall_client.get.return_value = {
            "orderedFirewallPolicyIds": {
                "beforeSystemDefined": ["one"],
                "afterSystemDefined": ["two"],
            }
        }

        result = run(get_firewall_policy_ordering("default", "zone-a", "zone-b"))

        assert result["orderedFirewallPolicyIds"]["beforeSystemDefined"] == ["one"]

    def test_update_ordering_dry_run(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import update_firewall_policy_ordering

        result = run(
            update_firewall_policy_ordering(
                site_id="default",
                source_zone_id="zone-a",
                destination_zone_id="zone-b",
                before_system_defined=["one"],
                after_system_defined=["two"],
                dry_run=True,
            )
        )

        assert result["dry_run"] is True
        firewall_client.put.assert_not_called()

    def test_update_ordering_success(self, firewall_client: AsyncMock) -> None:
        from src.tools.firewall_policies import update_firewall_policy_ordering

        firewall_client.put.return_value = {
            "orderedFirewallPolicyIds": {
                "beforeSystemDefined": ["one"],
                "afterSystemDefined": ["two"],
            }
        }

        result = run(
            update_firewall_policy_ordering(
                site_id="default",
                source_zone_id="zone-a",
                destination_zone_id="zone-b",
                before_system_defined=["one"],
                after_system_defined=["two"],
                confirm=True,
            )
        )

        assert result["orderedFirewallPolicyIds"]["afterSystemDefined"] == ["two"]

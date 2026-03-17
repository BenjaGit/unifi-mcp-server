"""Unit tests for get_firewall_policy_details tool."""

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


def run(coro):
    """Execute an async coroutine synchronously for tests."""
    return asyncio.run(coro)


# ── Sample data fixtures ──────────────────────────────────────────

ZONE_INTERNAL_ID = "zone-internal-001"
ZONE_IOT_ID = "zone-iot-002"
ZONE_VPN_ID = "zone-vpn-003"
ZONE_EXTERNAL_ID = "zone-external-004"

NETWORK_INTERN_ID = "net-intern-001"
NETWORK_BYOD_ID = "net-byod-002"
NETWORK_IOT_ID = "net-iot-003"
NETWORK_DEFAULT_ID = "net-default-004"

IP_GROUP_SONOS_ID = "ipg-sonos-001"
PORT_GROUP_FAMLY_ID = "pg-famly-001"

SAMPLE_ZONES = [
    {
        "id": ZONE_INTERNAL_ID,
        "name": "Internal",
        "networkIds": [NETWORK_DEFAULT_ID, NETWORK_INTERN_ID],
    },
    {"id": ZONE_IOT_ID, "name": "IoT", "networkIds": [NETWORK_IOT_ID, NETWORK_BYOD_ID]},
    {"id": ZONE_VPN_ID, "name": "VPN", "networkIds": []},
    {"id": ZONE_EXTERNAL_ID, "name": "External", "networkIds": []},
]

SAMPLE_NETWORKS = [
    {"id": NETWORK_DEFAULT_ID, "name": "Default", "vlanId": 1},
    {"id": NETWORK_INTERN_ID, "name": "INTERN", "vlanId": 333},
    {"id": NETWORK_BYOD_ID, "name": "BYOD", "vlanId": 555},
    {"id": NETWORK_IOT_ID, "name": "IOT", "vlanId": 444},
]

# Legacy networks use _id instead of id
SAMPLE_LEGACY_NETWORKS = [
    {"_id": "legacy-default", "name": "Default"},
    {"_id": "legacy-intern", "name": "INTERN"},
    {"_id": "legacy-byod", "name": "BYOD"},
    {"_id": "legacy-iot", "name": "IOT"},
]

SAMPLE_GROUPS = [
    {
        "_id": IP_GROUP_SONOS_ID,
        "name": "SONOS",
        "group_type": "address-group",
        "group_members": ["192.168.105.30-192.168.105.42"],
    },
    {
        "_id": PORT_GROUP_FAMLY_ID,
        "name": "Famlybi.com",
        "group_type": "port-group",
        "group_members": ["80", "443", "2025"],
    },
]


def _make_v2_policy(
    *,
    id: str = "policy-001",
    name: str = "Allow Intern → IoT (Sonos)",
    action: str = "ALLOW",
    enabled: bool = True,
    predefined: bool = False,
    protocol: str = "all",
    ip_version: str = "IPV4",
    source_zone_id: str = ZONE_INTERNAL_ID,
    source_matching_target: str = "NETWORK",
    source_network_ids: list[str] | None = None,
    source_client_macs: list[str] | None = None,
    dest_zone_id: str = ZONE_IOT_ID,
    dest_matching_target: str = "IP",
    dest_ip_group_id: str | None = None,
    dest_port_group_id: str | None = None,
    dest_ips: list[str] | None = None,
    dest_port: str | None = None,
) -> dict:
    return {
        "_id": id,
        "name": name,
        "action": action,
        "enabled": enabled,
        "predefined": predefined,
        "index": 10000,
        "protocol": protocol,
        "ip_version": ip_version,
        "connection_state_type": "ALL",
        "connection_states": [],
        "create_allow_respond": True,
        "logging": False,
        "match_ip_sec": False,
        "match_opposite_protocol": False,
        "icmp_typename": "ANY",
        "icmp_v6_typename": "ANY",
        "description": "",
        "origin_id": None,
        "origin_type": None,
        "source": {
            "zone_id": source_zone_id,
            "matching_target": source_matching_target,
            "matching_target_type": None,
            "port_matching_type": "ANY",
            "port": None,
            "match_opposite_ports": False,
            "ips": None,
            "match_opposite_ips": None,
            "network_ids": source_network_ids,
            "match_opposite_networks": False,
            "regions": None,
            "client_macs": source_client_macs,
            "match_mac": None,
        },
        "destination": {
            "zone_id": dest_zone_id,
            "matching_target": dest_matching_target,
            "matching_target_type": "OBJECT" if dest_ip_group_id else None,
            "port_matching_type": "SPECIFIC" if dest_port_group_id or dest_port else "ANY",
            "port": dest_port,
            "match_opposite_ports": False,
            "ips": dest_ips or [],
            "match_opposite_ips": False,
            "network_ids": None,
            "match_opposite_networks": None,
            "regions": None,
            "client_macs": None,
            "match_mac": None,
            "ip_group_id": dest_ip_group_id,
            "port_group_id": dest_port_group_id,
        },
        "schedule": {"mode": "ALWAYS"},
    }


SAMPLE_CUSTOM_POLICY = _make_v2_policy(
    source_network_ids=["legacy-intern"],
    dest_ip_group_id=IP_GROUP_SONOS_ID,
)

SAMPLE_BLOCK_POLICY = _make_v2_policy(
    id="policy-002",
    name="Block Default → IoT",
    action="BLOCK",
    source_matching_target="NETWORK",
    source_network_ids=["legacy-default"],
    dest_matching_target="ANY",
    dest_ip_group_id=None,
)

SYSTEM_POLICIES = [
    _make_v2_policy(id="sys-001", name="Allow All Traffic", predefined=True),
    _make_v2_policy(id="sys-002", name="Block All Traffic", predefined=True),
    _make_v2_policy(id="sys-003", name="Allow Return Traffic", predefined=True),
    _make_v2_policy(id="sys-004", name="Allow DNS", predefined=True),
    _make_v2_policy(id="sys-005", name="Allow Intern → IoT (Sonos) (Return)", predefined=True),
]


# ── Mock client ───────────────────────────────────────────────────


def make_mock_client(*, api_type: APIType = APIType.LOCAL) -> AsyncMock:
    """Create a reusable mock NetworkClient instance."""
    client = AsyncMock()
    client.settings = SimpleNamespace(api_type=api_type)
    client.is_authenticated = True
    client.authenticate = AsyncMock()
    client.resolve_site = AsyncMock(
        return_value=SimpleNamespace(name="default", uuid="uuid-default")
    )
    client.v2_path = MagicMock(
        side_effect=lambda site, ep: f"/proxy/network/v2/api/site/{site}/{ep}"
    )
    client.integration_path = MagicMock(
        side_effect=lambda uuid, ep: f"/integration/v1/sites/{uuid}/{ep}"
    )
    client.legacy_path = MagicMock(side_effect=lambda site, ep: f"/proxy/network/api/s/{site}/{ep}")
    client.get = AsyncMock()
    client.post = AsyncMock()
    return client


def _setup_client_responses(
    client: AsyncMock,
    *,
    policies: list[dict] | None = None,
    single_policy: dict | None = None,
) -> None:
    """Configure mock client .get() to return appropriate data per endpoint."""
    all_policies = (
        policies
        if policies is not None
        else [SAMPLE_CUSTOM_POLICY, SAMPLE_BLOCK_POLICY] + SYSTEM_POLICIES
    )

    async def mock_get(endpoint: str, **kwargs):
        if "firewall/zones" in endpoint:
            return SAMPLE_ZONES
        if "networks" in endpoint and "integration" in endpoint:
            return SAMPLE_NETWORKS
        if "rest/networkconf" in endpoint:
            return SAMPLE_LEGACY_NETWORKS
        if "rest/firewallgroup" in endpoint:
            return SAMPLE_GROUPS
        if "firewall-policies/" in endpoint and single_policy:
            return single_policy
        if "firewall-policies" in endpoint:
            return all_policies
        return []

    client.get = AsyncMock(side_effect=mock_get)


@pytest.fixture
def detail_client() -> Generator[AsyncMock, None, None]:
    client = make_mock_client()
    _setup_client_responses(client)
    with patch("src.tools.firewall_policy_details.get_network_client", return_value=client):
        yield client


# ── Tests ─────────────────────────────────────────────────────────


class TestGetFirewallPolicyDetails:
    """Tests for get_firewall_policy_details tool."""

    def test_returns_all_custom_policies(self, detail_client: AsyncMock) -> None:
        from src.tools.firewall_policy_details import get_firewall_policy_details

        result = run(get_firewall_policy_details(site_id="default"))

        # Should exclude system policies and (Return) policies
        assert len(result["policies"]) == 2
        names = [p["name"] for p in result["policies"]]
        assert "Allow Intern → IoT (Sonos)" in names
        assert "Block Default → IoT" in names
        # System policies should be filtered out
        assert "Allow All Traffic" not in names
        assert "Allow Intern → IoT (Sonos) (Return)" not in names

    def test_resolves_zone_names(self, detail_client: AsyncMock) -> None:
        from src.tools.firewall_policy_details import get_firewall_policy_details

        result = run(get_firewall_policy_details(site_id="default"))

        policy = next(p for p in result["policies"] if p["name"] == "Allow Intern → IoT (Sonos)")
        assert policy["source"]["zone_name"] == "Internal"
        assert policy["destination"]["zone_name"] == "IoT"

    def test_resolves_network_names(self, detail_client: AsyncMock) -> None:
        from src.tools.firewall_policy_details import get_firewall_policy_details

        result = run(get_firewall_policy_details(site_id="default"))

        policy = next(p for p in result["policies"] if p["name"] == "Allow Intern → IoT (Sonos)")
        assert "INTERN" in policy["source"]["network_names"]

    def test_resolves_ip_group(self, detail_client: AsyncMock) -> None:
        from src.tools.firewall_policy_details import get_firewall_policy_details

        result = run(get_firewall_policy_details(site_id="default"))

        policy = next(p for p in result["policies"] if p["name"] == "Allow Intern → IoT (Sonos)")
        ip_group = policy["destination"]["ip_group"]
        assert ip_group["name"] == "SONOS"
        assert "192.168.105.30-192.168.105.42" in ip_group["members"]

    def test_single_policy_by_id(self, detail_client: AsyncMock) -> None:
        from src.tools.firewall_policy_details import get_firewall_policy_details

        _setup_client_responses(detail_client, single_policy=SAMPLE_CUSTOM_POLICY)

        result = run(get_firewall_policy_details(site_id="default", policy_id="policy-001"))

        assert len(result["policies"]) == 1
        assert result["policies"][0]["name"] == "Allow Intern → IoT (Sonos)"

    def test_single_policy_returns_system_policy(self, detail_client: AsyncMock) -> None:
        """When requesting a specific policy_id, system policies should NOT be filtered."""
        from src.tools.firewall_policy_details import get_firewall_policy_details

        system_policy = _make_v2_policy(id="sys-001", name="Allow All Traffic", predefined=True)
        _setup_client_responses(detail_client, single_policy=system_policy)

        result = run(get_firewall_policy_details(site_id="default", policy_id="sys-001"))

        assert len(result["policies"]) == 1
        assert result["policies"][0]["name"] == "Allow All Traffic"

    def test_search_by_name(self, detail_client: AsyncMock) -> None:
        from src.tools.firewall_policy_details import get_firewall_policy_details

        result = run(get_firewall_policy_details(site_id="default", search="Sonos"))

        assert len(result["policies"]) == 1
        assert result["policies"][0]["name"] == "Allow Intern → IoT (Sonos)"

    def test_search_case_insensitive(self, detail_client: AsyncMock) -> None:
        from src.tools.firewall_policy_details import get_firewall_policy_details

        result = run(get_firewall_policy_details(site_id="default", search="sonos"))

        assert len(result["policies"]) == 1

    def test_search_no_results(self, detail_client: AsyncMock) -> None:
        from src.tools.firewall_policy_details import get_firewall_policy_details

        result = run(get_firewall_policy_details(site_id="default", search="nonexistent"))

        assert len(result["policies"]) == 0

    def test_search_block_policies(self, detail_client: AsyncMock) -> None:
        from src.tools.firewall_policy_details import get_firewall_policy_details

        result = run(get_firewall_policy_details(site_id="default", search="Block"))

        assert len(result["policies"]) == 1
        assert result["policies"][0]["name"] == "Block Default → IoT"

    def test_includes_groups_section(self, detail_client: AsyncMock) -> None:
        from src.tools.firewall_policy_details import get_firewall_policy_details

        result = run(get_firewall_policy_details(site_id="default"))

        assert "groups" in result
        group_names = [g["name"] for g in result["groups"]]
        assert "SONOS" in group_names
        assert "Famlybi.com" in group_names

    def test_includes_zones_section(self, detail_client: AsyncMock) -> None:
        from src.tools.firewall_policy_details import get_firewall_policy_details

        result = run(get_firewall_policy_details(site_id="default"))

        assert "zones" in result
        zone_names = [z["name"] for z in result["zones"]]
        assert "Internal" in zone_names
        assert "IoT" in zone_names

    def test_client_macs_preserved(self, detail_client: AsyncMock) -> None:
        from src.tools.firewall_policy_details import get_firewall_policy_details

        mac_policy = _make_v2_policy(
            id="policy-mac",
            name="BEC > Pi5",
            source_matching_target="CLIENT",
            source_client_macs=["94:bd:be:36:64:8a", "a0:9a:8e:33:6d:4e"],
            source_network_ids=None,
            dest_matching_target="NETWORK",
            dest_ip_group_id=None,
        )
        _setup_client_responses(detail_client, policies=[mac_policy])

        result = run(get_firewall_policy_details(site_id="default"))

        policy = result["policies"][0]
        assert policy["source"]["client_macs"] == ["94:bd:be:36:64:8a", "a0:9a:8e:33:6d:4e"]

    def test_port_group_resolved(self, detail_client: AsyncMock) -> None:
        from src.tools.firewall_policy_details import get_firewall_policy_details

        port_policy = _make_v2_policy(
            id="policy-port",
            name="Allow IoT → AWS",
            dest_zone_id=ZONE_VPN_ID,
            dest_matching_target="IP",
            dest_ips=["10.15.0.0/16"],
            dest_port_group_id=PORT_GROUP_FAMLY_ID,
        )
        _setup_client_responses(detail_client, policies=[port_policy])

        result = run(get_firewall_policy_details(site_id="default"))

        policy = result["policies"][0]
        port_group = policy["destination"]["port_group"]
        assert port_group["name"] == "Famlybi.com"
        assert "80" in port_group["members"]

    def test_requires_local_api(self) -> None:
        from src.tools.firewall_policy_details import get_firewall_policy_details

        client = make_mock_client(api_type=APIType.CLOUD_V1)
        with patch("src.tools.firewall_policy_details.get_network_client", return_value=client):
            with pytest.raises(NotImplementedError, match="local"):
                run(get_firewall_policy_details(site_id="default"))

    def test_policy_count_in_result(self, detail_client: AsyncMock) -> None:
        from src.tools.firewall_policy_details import get_firewall_policy_details

        result = run(get_firewall_policy_details(site_id="default"))

        assert result["total"] == 2

    def test_empty_policies(self, detail_client: AsyncMock) -> None:
        from src.tools.firewall_policy_details import get_firewall_policy_details

        _setup_client_responses(detail_client, policies=[])

        result = run(get_firewall_policy_details(site_id="default"))

        assert result["total"] == 0
        assert result["policies"] == []

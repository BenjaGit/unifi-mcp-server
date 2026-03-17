"""Tests for Site Manager tools."""

from unittest.mock import AsyncMock, patch

import pytest

from src.api.network_client import SiteInfo
from src.tools.site_manager import (
    compare_site_performance,
    get_cross_site_statistics,
    get_internet_health,
    get_site_health_summary,
    get_site_inventory,
    list_all_sites_aggregated,
    search_across_sites,
)
from src.utils import ResourceNotFoundError


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""

    # Use a simple object with real attributes instead of MagicMock
    # to avoid MagicMock comparison issues with httpx timeout handling
    class MockSettings:
        log_level = "INFO"
        site_manager_enabled = True
        api_key = "test-key"
        request_timeout = 30.0

        def get_headers(self):
            return {"X-API-Key": "test-key"}

    return MockSettings()


@pytest.fixture
def mock_settings_disabled():
    """Create mock settings with site manager disabled."""

    # Use a simple object with real attributes instead of MagicMock
    class MockSettings:
        log_level = "INFO"
        site_manager_enabled = False
        api_key = "test-key"
        request_timeout = 30.0

        def get_headers(self):
            return {"X-API-Key": "test-key"}

    return MockSettings()


# =============================================================================
# Task 4.1: Test list_all_sites_aggregated
# =============================================================================


@pytest.mark.asyncio
async def test_list_all_sites_aggregated_success():
    """Test successful retrieval of aggregated sites list."""
    mock_response = {
        "data": [
            {
                "site_id": "site-1",
                "name": "Main Office",
                "devices": 5,
                "clients": 25,
            },
            {
                "site_id": "site-2",
                "name": "Branch Office",
                "devices": 3,
                "clients": 10,
            },
        ]
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_all_sites_aggregated()

        assert len(result) == 2
        assert result[0]["site_id"] == "site-1"
        assert result[0]["name"] == "Main Office"
        assert result[1]["site_id"] == "site-2"
        mock_client.list_sites.assert_called_once()


@pytest.mark.asyncio
async def test_list_all_sites_aggregated_empty():
    """Test retrieval when no sites exist."""
    mock_response = {"data": []}

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_all_sites_aggregated()

        assert result == []
        mock_client.list_sites.assert_called_once()


@pytest.mark.asyncio
async def test_list_all_sites_aggregated_disabled():
    """Test that function raises when site manager is disabled."""
    with pytest.raises(ValueError) as excinfo:
        await list_all_sites_aggregated()

    assert "Site Manager API is not enabled" in str(excinfo.value)


@pytest.mark.asyncio
async def test_list_all_sites_aggregated_alternate_response_format():
    """Test handling of 'sites' key instead of 'data'."""
    mock_response = {
        "sites": [
            {
                "site_id": "site-1",
                "name": "Office",
            }
        ]
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_all_sites_aggregated()

        assert len(result) == 1
        assert result[0]["site_id"] == "site-1"


# =============================================================================
# Task 4.2: Test get_internet_health
# =============================================================================


def _make_health_mock(subsystems: list[dict]) -> AsyncMock:
    """Helper: create a NetworkClient mock returning the given subsystems."""
    mock_client = AsyncMock()
    mock_client.authenticate = AsyncMock()
    mock_client.resolve_site = AsyncMock(return_value=AsyncMock(name="default"))
    mock_client.legacy_path = lambda site, path: f"/api/s/{site}/{path}"
    mock_client.get = AsyncMock(return_value=subsystems)  # UniFiClient auto-unwraps data key
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()
    return mock_client


@pytest.mark.asyncio
async def test_get_internet_health_all_sites():
    """Test internet health retrieval defaults to 'default' site."""
    subsystems = [
        {
            "subsystem": "www",
            "status": "ok",
            "latency": 25,
            "xput_up": 100,
            "xput_down": 500,
            "drops": 0,
            "speedtest_lastrun": 1704412800,
        },
        {"subsystem": "wan", "uptime_stats": {"WAN": {"availability": 100}}},
    ]

    with patch("src.tools.site_manager.get_network_client") as mock_client_class:
        mock_client_class.return_value = _make_health_mock(subsystems)

        result = await get_internet_health()

        assert result["status"] == "healthy"
        assert result["latency_ms"] == 25.0
        assert result["bandwidth_down_mbps"] == 500.0
        assert result["packet_loss_percent"] == 0.0


@pytest.mark.asyncio
async def test_get_internet_health_specific_site():
    """Test internet health retrieval for a specific site."""
    subsystems = [
        {
            "subsystem": "www",
            "status": "ok",
            "latency": 15,
            "xput_up": 50,
            "xput_down": 200,
            "drops": 0,
            "speedtest_lastrun": 1704412800,
        },
        {"subsystem": "wan", "uptime_stats": {"WAN": {"availability": 100}}},
    ]

    with patch("src.tools.site_manager.get_network_client") as mock_client_class:
        mock_client_class.return_value = _make_health_mock(subsystems)

        result = await get_internet_health(site_id="site-1")

        assert result["site_id"] == "site-1"
        assert result["status"] == "healthy"
        assert result["bandwidth_up_mbps"] == 50.0


@pytest.mark.asyncio
async def test_get_internet_health_degraded():
    """Test internet health when drops > 0 results in degraded status."""
    subsystems = [
        {
            "subsystem": "www",
            "status": "ok",
            "latency": 150,
            "xput_up": 10,
            "xput_down": 50,
            "drops": 4,
            "speedtest_lastrun": 1704412800,
        },
        {"subsystem": "wan", "uptime_stats": {"WAN": {"availability": 95}}},
    ]

    with patch("src.tools.site_manager.get_network_client") as mock_client_class:
        mock_client_class.return_value = _make_health_mock(subsystems)

        result = await get_internet_health()

        assert result["status"] == "degraded"
        assert result["packet_loss_percent"] == 5.0


# =============================================================================
# Task 4.3: Test get_site_health_summary and get_cross_site_statistics
# =============================================================================


@pytest.mark.asyncio
async def test_get_site_health_summary_specific_site():
    """Test health summary for a specific site."""
    mock_response = {
        "siteId": "site-1",
        "meta": {"desc": "Main Office", "name": "main"},
        "statistics": {
            "counts": {
                "totalDevice": 5,
                "offlineDevice": 0,
                "offlineGatewayDevice": 0,
                "wifiClient": 20,
                "wiredClient": 5,
            },
            "percentages": {"wanUptime": 99.9},
        },
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_site_health = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_site_health_summary(site_id="site-1")

        assert result["site_id"] == "site-1"
        assert result["site_name"] == "Main Office"
        assert result["status"] == "healthy"
        assert result["devices_online"] == 5
        assert result["clients_active"] == 25
        mock_client.get_site_health.assert_called_once_with("site-1")


@pytest.mark.asyncio
async def test_get_site_health_summary_specific_site_fallback_from_network_id():
    """Map network site UUID to Site Manager entry via resolved site name."""
    network_site_id = "88f7af54-98f8-306a-a1c7-c9349722b1f6"
    mock_response = {
        "data": [
            {
                "siteId": "65c53d85d0f2204f9bd44b10",
                "meta": {"desc": "Default", "name": "default"},
                "statistics": {
                    "counts": {
                        "totalDevice": 2,
                        "offlineDevice": 0,
                        "offlineGatewayDevice": 0,
                        "wifiClient": 3,
                        "wiredClient": 1,
                    },
                    "percentages": {"wanUptime": 100.0},
                },
            }
        ]
    }

    with (
        patch("src.tools.site_manager.get_site_manager_client") as mock_client_class,
        patch("src.tools.site_manager.get_network_client") as mock_network_client,
    ):
        mock_client = AsyncMock()
        mock_client.get_site_health = AsyncMock(
            side_effect=[
                ResourceNotFoundError("site", network_site_id),
                mock_response,
            ]
        )
        mock_client_class.return_value = mock_client

        network_client = AsyncMock()
        network_client.is_authenticated = True
        network_client.resolve_site = AsyncMock(
            return_value=SiteInfo(name="default", uuid=network_site_id)
        )
        mock_network_client.return_value = network_client

        result = await get_site_health_summary(site_id=network_site_id)

        assert result["site_id"] == "65c53d85d0f2204f9bd44b10"
        assert result["site_name"] == "Default"
        assert result["status"] == "healthy"
        assert mock_client.get_site_health.call_count == 2


@pytest.mark.asyncio
async def test_get_site_health_summary_all_sites():
    """Test health summary for all sites."""
    mock_response = {
        "data": [
            {
                "siteId": "site-1",
                "meta": {"desc": "Main Office", "name": "main"},
                "statistics": {
                    "counts": {
                        "totalDevice": 5,
                        "offlineDevice": 0,
                        "offlineGatewayDevice": 0,
                        "wifiClient": 20,
                        "wiredClient": 5,
                    },
                    "percentages": {"wanUptime": 99.9},
                },
            },
            {
                "siteId": "site-2",
                "meta": {"desc": "Branch Office", "name": "branch"},
                "statistics": {
                    "counts": {
                        "totalDevice": 3,
                        "offlineDevice": 1,
                        "offlineGatewayDevice": 0,
                        "wifiClient": 8,
                        "wiredClient": 2,
                    },
                    "percentages": {"wanUptime": 95.0},
                },
            },
        ]
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_site_health = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_site_health_summary()

        assert isinstance(result, dict)
        assert "sites" in result
        assert len(result["sites"]) == 2
        assert result["sites"][0]["site_id"] == "site-1"
        assert result["sites"][1]["status"] == "degraded"
        mock_client.get_site_health.assert_called_once_with(None)


@pytest.mark.asyncio
async def test_get_site_health_summary_disabled():
    """Test that function raises when site manager is disabled."""
    with pytest.raises(ValueError) as excinfo:
        await get_site_health_summary()

    assert "Site Manager API is not enabled" in str(excinfo.value)


@pytest.mark.asyncio
async def test_get_cross_site_statistics_success():
    """Test cross-site statistics aggregation."""
    mock_sites_response = {
        "data": [
            {"site_id": "site-1", "name": "Site 1"},
            {"site_id": "site-2", "name": "Site 2"},
            {"site_id": "site-3", "name": "Site 3"},
        ]
    }
    mock_health_response = {
        "data": [
            {
                "site_id": "site-1",
                "site_name": "Site 1",
                "status": "healthy",
                "devices_online": 5,
                "devices_total": 5,
                "clients_active": 25,
                "uptime_percentage": 99.9,
                "last_updated": "2026-01-05T00:00:00Z",
            },
            {
                "site_id": "site-2",
                "site_name": "Site 2",
                "status": "degraded",
                "devices_online": 2,
                "devices_total": 3,
                "clients_active": 10,
                "uptime_percentage": 95.0,
                "last_updated": "2026-01-05T00:00:00Z",
            },
            {
                "site_id": "site-3",
                "site_name": "Site 3",
                "status": "down",
                "devices_online": 0,
                "devices_total": 2,
                "clients_active": 0,
                "uptime_percentage": 0.0,
                "last_updated": "2026-01-05T00:00:00Z",
            },
        ]
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_sites_response)
        mock_client.get_site_health = AsyncMock(return_value=mock_health_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_cross_site_statistics()

        assert result["total_sites"] == 3
        assert result["sites_healthy"] == 1
        assert result["sites_degraded"] == 1
        assert result["sites_down"] == 1
        assert result["total_devices"] == 10  # 5 + 3 + 2
        assert result["devices_online"] == 7  # 5 + 2 + 0
        assert result["total_clients"] == 35  # 25 + 10 + 0
        assert len(result["site_summaries"]) == 3


@pytest.mark.asyncio
async def test_get_cross_site_statistics_handles_raw_site_manager_payload():
    """Aggregate stats when get_site_health returns raw /v1/sites entries."""
    mock_sites_response = {
        "data": [
            {"siteId": "site-1", "meta": {"desc": "Site 1"}},
            {"siteId": "site-2", "meta": {"desc": "Site 2"}},
        ]
    }
    mock_health_response = {
        "data": [
            {
                "siteId": "site-1",
                "meta": {"desc": "Site 1", "name": "site1"},
                "statistics": {
                    "counts": {
                        "totalDevice": 5,
                        "offlineDevice": 0,
                        "offlineGatewayDevice": 0,
                        "wifiClient": 20,
                        "wiredClient": 5,
                    },
                    "percentages": {"wanUptime": 99.9},
                },
            },
            {
                "siteId": "site-2",
                "meta": {"desc": "Site 2", "name": "site2"},
                "statistics": {
                    "counts": {
                        "totalDevice": 3,
                        "offlineDevice": 1,
                        "offlineGatewayDevice": 0,
                        "wifiClient": 8,
                        "wiredClient": 2,
                    },
                    "percentages": {"wanUptime": 95.0},
                },
            },
        ]
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_sites_response)
        mock_client.get_site_health = AsyncMock(return_value=mock_health_response)
        mock_client_class.return_value = mock_client

        result = await get_cross_site_statistics()

        assert result["total_sites"] == 2
        assert result["sites_healthy"] == 1
        assert result["sites_degraded"] == 1
        assert result["sites_down"] == 0
        assert result["total_devices"] == 8
        assert result["devices_online"] == 7
        assert result["total_clients"] == 35
        assert len(result["site_summaries"]) == 2


@pytest.mark.asyncio
async def test_get_cross_site_statistics_empty():
    """Test cross-site statistics with no sites."""
    mock_sites_response = {"data": []}
    mock_health_response = {"data": []}

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_sites_response)
        mock_client.get_site_health = AsyncMock(return_value=mock_health_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_cross_site_statistics()

        assert result["total_sites"] == 0
        assert result["sites_healthy"] == 0
        assert result["total_devices"] == 0
        assert len(result["site_summaries"]) == 0


@pytest.mark.asyncio
async def test_get_cross_site_statistics_disabled():
    """Test that function raises when site manager is disabled."""
    with pytest.raises(ValueError) as excinfo:
        await get_cross_site_statistics()

    assert "Site Manager API is not enabled" in str(excinfo.value)


# =============================================================================
# Task 4.5: Test get_site_inventory
# =============================================================================


@pytest.mark.asyncio
async def test_get_site_inventory_specific_site():
    """Test inventory retrieval for a specific site using /v1/sites statistics."""
    mock_site = {
        "siteId": "site-1",
        "meta": {"desc": "Main Office"},
        "statistics": {
            "counts": {
                "totalDevice": 15,
                "wifiDevice": 8,
                "wiredDevice": 7,
                "offlineDevice": 0,
                "wifiClient": 50,
                "wiredClient": 25,
                "lanConfiguration": 3,
                "wifiConfiguration": 2,
                "wanConfiguration": 1,
            }
        },
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_site_health = AsyncMock(return_value=mock_site)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_site_inventory(site_id="site-1")

        assert result["site_id"] == "site-1"
        assert result["site_name"] == "Main Office"
        assert result["total_devices"] == 15
        assert result["wifi_clients"] == 50
        assert result["wired_clients"] == 25
        assert result["total_clients"] == 75
        mock_client.get_site_health.assert_called_once_with("site-1")


@pytest.mark.asyncio
async def test_get_site_inventory_all_sites():
    """Test inventory retrieval for all sites."""
    mock_response = {
        "data": [
            {
                "siteId": "site-1",
                "meta": {"desc": "Office 1"},
                "statistics": {
                    "counts": {
                        "totalDevice": 10,
                        "wifiDevice": 6,
                        "wiredDevice": 4,
                        "offlineDevice": 0,
                        "wifiClient": 30,
                        "wiredClient": 20,
                        "lanConfiguration": 2,
                        "wifiConfiguration": 1,
                        "wanConfiguration": 1,
                    }
                },
            },
            {
                "siteId": "site-2",
                "meta": {"desc": "Office 2"},
                "statistics": {
                    "counts": {
                        "totalDevice": 5,
                        "wifiDevice": 3,
                        "wiredDevice": 2,
                        "offlineDevice": 1,
                        "wifiClient": 10,
                        "wiredClient": 5,
                        "lanConfiguration": 1,
                        "wifiConfiguration": 1,
                        "wanConfiguration": 1,
                    }
                },
            },
        ]
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sites = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_site_inventory()

        assert isinstance(result, dict)
        assert "sites" in result
        assert len(result["sites"]) == 2
        assert result["sites"][0]["site_id"] == "site-1"
        assert result["sites"][0]["total_devices"] == 10
        assert result["sites"][1]["site_id"] == "site-2"
        assert result["sites"][1]["total_clients"] == 15  # 10 wifi + 5 wired
        mock_client.list_sites.assert_called_once()


@pytest.mark.asyncio
async def test_get_site_inventory_disabled():
    """Test that function raises when site manager is disabled."""
    with pytest.raises(ValueError) as excinfo:
        await get_site_inventory()

    assert "Site Manager API is not enabled" in str(excinfo.value)


@pytest.mark.asyncio
async def test_get_site_inventory_empty_devices():
    """Test inventory with no devices."""
    mock_site = {
        "siteId": "site-1",
        "meta": {"desc": "New Site"},
        "statistics": {
            "counts": {
                "totalDevice": 0,
                "wifiDevice": 0,
                "wiredDevice": 0,
                "offlineDevice": 0,
                "wifiClient": 0,
                "wiredClient": 0,
                "lanConfiguration": 1,
                "wifiConfiguration": 0,
                "wanConfiguration": 0,
            }
        },
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_site_health = AsyncMock(return_value=mock_site)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_site_inventory(site_id="site-1")

        assert result["total_devices"] == 0
        assert result["total_clients"] == 0


# =============================================================================
# Task 4.6: Test compare_site_performance
# =============================================================================


@pytest.mark.asyncio
async def test_compare_site_performance_success():
    """Test successful performance comparison across sites."""
    mock_health_response = {
        "data": [
            {
                "siteId": "site-1",
                "meta": {"desc": "Best Site"},
                "statistics": {
                    "counts": {
                        "totalDevice": 10,
                        "offlineDevice": 0,
                        "offlineGatewayDevice": 0,
                        "wifiClient": 40,
                        "wiredClient": 10,
                    },
                    "percentages": {"wanUptime": 99.9},
                },
            },
            {
                "siteId": "site-2",
                "meta": {"desc": "Average Site"},
                "statistics": {
                    "counts": {
                        "totalDevice": 10,
                        "offlineDevice": 2,
                        "offlineGatewayDevice": 0,
                        "wifiClient": 30,
                        "wiredClient": 10,
                    },
                    "percentages": {"wanUptime": 95.0},
                },
            },
            {
                "siteId": "site-3",
                "meta": {"desc": "Worst Site"},
                "statistics": {
                    "counts": {
                        "totalDevice": 10,
                        "offlineDevice": 5,
                        "offlineGatewayDevice": 0,
                        "wifiClient": 15,
                        "wiredClient": 5,
                    },
                    "percentages": {"wanUptime": 80.0},
                },
            },
        ]
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_site_health = AsyncMock(return_value=mock_health_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await compare_site_performance()

        assert result["total_sites"] == 3
        assert result["best_performing_site"]["site_id"] == "site-1"
        assert result["worst_performing_site"]["site_id"] == "site-3"
        assert result["average_uptime"] == pytest.approx((99.9 + 95.0 + 80.0) / 3)
        assert len(result["site_metrics"]) == 3


@pytest.mark.asyncio
async def test_compare_site_performance_empty():
    """Test performance comparison with no sites."""
    mock_health_response = {"data": []}
    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_site_health = AsyncMock(return_value=mock_health_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await compare_site_performance()

        assert result["total_sites"] == 0
        assert result["best_performing_site"] is None
        assert result["worst_performing_site"] is None
        assert result["average_uptime"] == 0.0


@pytest.mark.asyncio
async def test_compare_site_performance_disabled():
    """Test that function raises when site manager is disabled."""
    with pytest.raises(ValueError) as excinfo:
        await compare_site_performance()

    assert "Site Manager API is not enabled" in str(excinfo.value)


@pytest.mark.asyncio
async def test_compare_site_performance_single_site():
    """Test performance comparison with only one site."""
    mock_health_response = {
        "data": [
            {
                "siteId": "site-1",
                "meta": {"desc": "Only Site"},
                "statistics": {
                    "counts": {
                        "totalDevice": 10,
                        "offlineDevice": 0,
                        "offlineGatewayDevice": 0,
                        "wifiClient": 40,
                        "wiredClient": 10,
                    },
                    "percentages": {"wanUptime": 99.5},
                },
            }
        ]
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_site_health = AsyncMock(return_value=mock_health_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await compare_site_performance()

        assert result["total_sites"] == 1
        assert result["best_performing_site"]["site_id"] == "site-1"
        assert result["worst_performing_site"]["site_id"] == "site-1"
        assert result["average_uptime"] == 99.5


# =============================================================================
# Task 4.7: Test search_across_sites
# =============================================================================


@pytest.mark.asyncio
async def test_search_across_sites_device():
    """Test searching for devices across sites using /v1/devices endpoint."""
    mock_response = {
        "data": [
            {
                "hostId": "host-1",
                "hostName": "Office 1",
                "devices": [
                    {
                        "id": "AABBCCDDEEF01",
                        "mac": "aa:bb:cc:dd:ee:01",
                        "name": "AP-Living-Room",
                        "model": "UAP-AC",
                        "status": "online",
                    },
                    {
                        "id": "AABBCCDDEEF02",
                        "mac": "aa:bb:cc:dd:ee:02",
                        "name": "Switch-Main",
                        "model": "USW-24",
                        "status": "online",
                    },
                ],
            },
            {
                "hostId": "host-2",
                "hostName": "Office 2",
                "devices": [
                    {
                        "id": "AABBCCDDEEF03",
                        "mac": "aa:bb:cc:dd:ee:03",
                        "name": "AP-Conference",
                        "model": "UAP-AC",
                        "status": "online",
                    },
                ],
            },
        ]
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_devices = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await search_across_sites(query="living", search_type="device")

        assert result["total_results"] == 1
        assert result["search_query"] == "living"
        assert result["result_type"] == "device"
        assert result["results"][0]["type"] == "device"
        assert result["results"][0]["host_id"] == "host-1"
        assert result["results"][0]["resource"]["name"] == "AP-Living-Room"


@pytest.mark.asyncio
async def test_search_across_sites_all():
    """Test search_type='all' searches devices (device search is the only supported type)."""
    mock_response = {
        "data": [
            {
                "hostId": "host-1",
                "hostName": "Office 1",
                "devices": [
                    {
                        "id": "AABBCCDDEEF01",
                        "mac": "aa:bb:cc:dd:ee:01",
                        "name": "Test-Device",
                        "model": "UDM",
                        "status": "online",
                    },
                ],
            }
        ]
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_devices = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await search_across_sites(query="test", search_type="all")

        assert result["total_results"] == 1
        assert result["result_type"] == "device"
        assert result["results"][0]["type"] == "device"


@pytest.mark.asyncio
async def test_search_across_sites_no_results():
    """Test searching with no matching results."""
    mock_response = {
        "data": [
            {
                "hostId": "host-1",
                "hostName": "Office 1",
                "devices": [
                    {
                        "id": "AABBCCDDEEF01",
                        "mac": "aa:bb:cc:dd:ee:01",
                        "name": "AP-Main",
                        "model": "UAP",
                        "status": "online",
                    },
                ],
            }
        ]
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_devices = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await search_across_sites(query="nonexistent", search_type="device")

        assert result["total_results"] == 0
        assert len(result["results"]) == 0


@pytest.mark.asyncio
async def test_search_across_sites_invalid_type():
    """Test searching with invalid search type."""
    with pytest.raises(ValueError) as excinfo:
        await search_across_sites(query="test", search_type="invalid")

    assert "search_type must be one of" in str(excinfo.value)


@pytest.mark.asyncio
async def test_search_across_sites_client_type_raises():
    """Test that client search type raises ValueError (requires local Network API)."""
    with pytest.raises(ValueError) as excinfo:
        await search_across_sites(query="test", search_type="client")

    assert "local Network API" in str(excinfo.value)


@pytest.mark.asyncio
async def test_search_across_sites_disabled():
    """Test that function raises when site manager is disabled."""
    with pytest.raises(ValueError) as excinfo:
        await search_across_sites(query="test")

    assert "Site Manager API is not enabled" in str(excinfo.value)


@pytest.mark.asyncio
async def test_search_across_sites_mac_address():
    """Test searching by MAC address."""
    mock_response = {
        "data": [
            {
                "hostId": "host-1",
                "hostName": "Office 1",
                "devices": [
                    {
                        "id": "AABBCCDDEEF01",
                        "mac": "aa:bb:cc:dd:ee:01",
                        "name": "AP-Main",
                        "model": "UAP",
                        "status": "online",
                    },
                ],
            }
        ]
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_devices = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await search_across_sites(query="aa:bb:cc:dd:ee:01", search_type="device")

        assert result["total_results"] == 1
        assert result["results"][0]["resource"]["mac"] == "aa:bb:cc:dd:ee:01"


# =============================================================================
# Tests for ISP Metrics Tools (added 2026-02-16)
# =============================================================================


@pytest.mark.asyncio
async def test_get_isp_metrics_success():
    """Test successful retrieval of ISP metrics by interval type."""
    from src.tools.site_manager import get_isp_metrics

    mock_response = {
        "data": [
            {
                "metricType": "5m",
                "hostId": "host-1",
                "siteId": "site-1",
                "periods": [
                    {
                        "metricTime": "2026-02-16T12:00:00Z",
                        "data": {
                            "wan": {
                                "avgLatency": 15,
                                "maxLatency": 20,
                                "download_kbps": 500000,
                                "upload_kbps": 100000,
                                "packetLoss": 0,
                                "uptime": 100,
                                "ispAsn": "12578",
                                "ispName": "Example ISP",
                            }
                        },
                    }
                ],
            }
        ]
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_isp_metrics = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_isp_metrics(metric_type="5m", duration="24h")

        assert result == mock_response
        mock_client.get_isp_metrics.assert_called_once_with(
            "5m", duration="24h", begin_timestamp=None, end_timestamp=None
        )


@pytest.mark.asyncio
async def test_query_isp_metrics_success():
    """Test successful querying of ISP metrics for a specific site."""
    from src.tools.site_manager import query_isp_metrics

    mock_response = {
        "data": [
            {
                "metricType": "5m",
                "hostId": "host-1",
                "siteId": "site-1",
                "periods": [
                    {
                        "metricTime": "2026-02-16T12:00:00Z",
                        "data": {
                            "wan": {
                                "avgLatency": 15,
                                "download_kbps": 500000,
                                "upload_kbps": 100000,
                                "packetLoss": 0,
                                "uptime": 100,
                                "ispName": "ISP 1",
                            }
                        },
                    }
                ],
            }
        ]
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.query_isp_metrics = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await query_isp_metrics(
            metric_type="5m",
            host_id="host-1",
            site_id="site-1",
            begin_timestamp="2026-02-16T00:00:00Z",
        )

        assert result == mock_response
        mock_client.query_isp_metrics.assert_called_once_with(
            "5m",
            body={
                "sites": [
                    {
                        "hostId": "host-1",
                        "siteId": "site-1",
                        "beginTimestamp": "2026-02-16T00:00:00Z",
                    }
                ]
            },
        )


@pytest.mark.asyncio
async def test_query_isp_metrics_no_timestamps():
    """Test query_isp_metrics builds body without optional timestamps."""
    from src.tools.site_manager import query_isp_metrics

    mock_response = {"data": []}

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.query_isp_metrics = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await query_isp_metrics(host_id="host-1", site_id="site-1")

        assert result == mock_response
        mock_client.query_isp_metrics.assert_called_once_with(
            "5m",
            body={"sites": [{"hostId": "host-1", "siteId": "site-1"}]},
        )


# =============================================================================
# Tests for SD-WAN Configuration Tools (added 2026-02-16)
# =============================================================================


@pytest.mark.asyncio
async def test_list_sdwan_configs_success():
    """Test successful retrieval of SD-WAN configurations."""
    from src.tools.site_manager import list_sdwan_configs

    mock_response = {
        "data": [
            {
                "config_id": "config-1",
                "name": "Hub-Spoke Config",
                "topology_type": "hub-spoke",
                "hub_site_ids": ["site-1"],
                "spoke_site_ids": ["site-2", "site-3"],
                "failover_enabled": True,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-02-01T00:00:00Z",
                "status": "active",
            }
        ]
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_sdwan_configs = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_sdwan_configs()

        assert len(result) == 1
        assert result[0]["config_id"] == "config-1"
        assert result[0]["topology_type"] == "hub-spoke"
        mock_client.list_sdwan_configs.assert_called_once()


@pytest.mark.asyncio
async def test_get_sdwan_config_success():
    """Test successful retrieval of SD-WAN config by ID."""
    from src.tools.site_manager import get_sdwan_config

    mock_response = {
        "data": {
            "config_id": "config-1",
            "name": "Hub-Spoke Config",
            "topology_type": "hub-spoke",
            "hub_site_ids": ["site-1"],
            "spoke_site_ids": ["site-2"],
            "failover_enabled": True,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-02-01T00:00:00Z",
            "status": "active",
        }
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_sdwan_config = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_sdwan_config("config-1")

        assert result["config_id"] == "config-1"
        assert result["name"] == "Hub-Spoke Config"
        mock_client.get_sdwan_config.assert_called_once_with("config-1")


@pytest.mark.asyncio
async def test_get_sdwan_config_status_success():
    """Test successful retrieval of SD-WAN config status."""
    from src.tools.site_manager import get_sdwan_config_status

    mock_response = {
        "data": {
            "config_id": "config-1",
            "deployment_status": "deployed",
            "sites_deployed": 3,
            "sites_total": 3,
            "last_deployment_at": "2026-02-15T10:00:00Z",
            "error_message": None,
        }
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_sdwan_config_status = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_sdwan_config_status("config-1")

        assert result["config_id"] == "config-1"
        assert result["deployment_status"] == "deployed"
        assert result["sites_deployed"] == 3
        mock_client.get_sdwan_config_status.assert_called_once_with("config-1")


# =============================================================================
# Tests for Host Management Tools (added 2026-02-16)
# =============================================================================


@pytest.mark.asyncio
async def test_list_hosts_success():
    """Test successful retrieval of hosts list with API-realistic payload."""
    from src.tools.site_manager import list_hosts

    mock_response = {
        "data": [
            {
                "id": "70A741F979A7:123456",
                "hardwareId": "f0f71a57-8d7f-5da2-a91c-bb085e91ddb3",
                "type": "console",
                "ipAddress": "192.168.1.1",
                "owner": True,
                "isBlocked": False,
                "registrationTime": "2023-12-06T16:30:30Z",
                "lastConnectionStateChange": "2026-02-16T12:00:00Z",
                "latestBackupTime": "",
            }
        ]
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.list_hosts = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await list_hosts()

        assert len(result) == 1
        assert result[0]["host_id"] == "70A741F979A7:123456"
        assert result[0]["ip_address"] == "192.168.1.1"
        assert result[0]["type"] == "console"
        mock_client.list_hosts.assert_called_once_with(None, None)


@pytest.mark.asyncio
async def test_get_host_success():
    """Test successful retrieval of host details with API-realistic payload."""
    from src.tools.site_manager import get_host

    mock_response = {
        "data": {
            "id": "70A741F979A7:123456",
            "hardwareId": "f0f71a57-8d7f-5da2-a91c-bb085e91ddb3",
            "type": "console",
            "ipAddress": "192.168.1.1",
            "owner": True,
            "isBlocked": False,
            "registrationTime": "2023-12-06T16:30:30Z",
            "lastConnectionStateChange": "2026-02-16T12:00:00Z",
            "latestBackupTime": "",
        }
    }

    with patch("src.tools.site_manager.get_site_manager_client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get_host = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client_class.return_value = mock_client

        result = await get_host("70A741F979A7:123456")

        assert result["host_id"] == "70A741F979A7:123456"
        assert result["ip_address"] == "192.168.1.1"
        assert result["last_seen"] == "2026-02-16T12:00:00Z"
        mock_client.get_host.assert_called_once_with("70A741F979A7:123456")

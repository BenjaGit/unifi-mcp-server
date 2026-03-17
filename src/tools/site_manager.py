"""Site Manager API tools for multi-site management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Literal

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client, get_site_manager_client
from ..api.site_manager_client import SiteManagerClient
from ..models.site_manager import (
    CrossSitePerformanceComparison,
    CrossSiteSearchResult,
    CrossSiteStatistics,
    Host,
    InternetHealthMetrics,
    SDWANConfig,
    SDWANConfigStatus,
    SiteHealthSummary,
    SiteInventory,
    SitePerformanceMetrics,
)
from ..utils import ResourceNotFoundError, get_logger, validate_site_id

logger = get_logger(__name__)
provider = LocalProvider()
SiteStatus = Literal["healthy", "degraded", "down"]

__all__ = [
    "provider",
    "list_all_sites_aggregated",
    "get_internet_health",
    "get_site_health_summary",
    "get_cross_site_statistics",
    "get_site_inventory",
    "compare_site_performance",
    "search_across_sites",
    "get_isp_metrics",
    "query_isp_metrics",
    "list_sdwan_configs",
    "get_sdwan_config",
    "get_sdwan_config_status",
    "list_hosts",
    "get_host",
]


def _require_site_manager_client() -> SiteManagerClient:
    """Return pooled Site Manager client when enabled."""
    try:
        client = get_site_manager_client()
    except RuntimeError as exc:
        raise ValueError("Site Manager API is not enabled. Configure UNIFI_REMOTE_API_KEY") from exc

    settings = getattr(client, "settings", None)
    if not getattr(settings, "site_manager_enabled", False):
        raise ValueError("Site Manager API is not enabled. Configure UNIFI_REMOTE_API_KEY")

    return client


@asynccontextmanager
async def _site_manager_client_context() -> AsyncIterator[SiteManagerClient]:
    """Yield pooled Site Manager client for compatibility."""
    yield _require_site_manager_client()


@provider.tool()
async def list_all_sites_aggregated() -> list[dict[str, Any]]:
    """List all sites with aggregated stats from Site Manager API.

    Args:
        settings: Application settings

    Returns:
        List of sites with aggregated statistics
    """

    client = _require_site_manager_client()
    logger.info("Retrieving aggregated site list from Site Manager API")

    response = await client.list_sites()
    sites_data = response.get("data", response.get("sites", []))

    # Enhance with aggregated stats if available
    sites: list[dict[str, Any]] = []
    for site in sites_data:
        sites.append(site)

    return sites


@provider.tool()
async def get_internet_health(site_id: str | None = None) -> dict[str, Any]:
    """Get internet health metrics from the local Network API.

    Uses the local gateway's stat/health endpoint, extracting the www and wan
    subsystems. The Site Manager cloud API does not have a working internet/health
    endpoint, so this always uses the local API regardless of site_manager_enabled.

    Args:
        settings: Application settings
        site_id: Site identifier. Defaults to "default".

    Returns:
        Internet health metrics
    """
    resolved_site_id = validate_site_id(site_id or "default")
    logger.info(f"Retrieving internet health metrics (site_id={resolved_site_id})")

    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(resolved_site_id)
    response = await client.get(client.legacy_path(site.name, "stat/health"))
    subsystems: list[dict[str, Any]] = (
        response if isinstance(response, list) else response.get("data", [])
    )

    www = next((s for s in subsystems if s.get("subsystem") == "www"), {})
    wan = next((s for s in subsystems if s.get("subsystem") == "wan"), {})

    wan_uptime = wan.get("uptime_stats", {}).get("WAN", {})
    availability = wan_uptime.get("availability", 100)
    speedtest_lastrun = www.get("speedtest_lastrun")
    last_tested = (
        datetime.fromtimestamp(speedtest_lastrun, tz=timezone.utc).isoformat()
        if speedtest_lastrun
        else datetime.now(timezone.utc).isoformat()
    )

    status: SiteStatus
    if www.get("status") != "ok":
        status = "down"
    elif www.get("drops", 0) > 0 or availability < 100:
        status = "degraded"
    else:
        status = "healthy"

    return InternetHealthMetrics(
        site_id=resolved_site_id,
        latency_ms=float(www.get("latency", 0)) or None,
        packet_loss_percent=round(max(0.0, 100.0 - availability), 2),
        jitter_ms=None,
        bandwidth_up_mbps=float(www.get("xput_up", 0)) or None,
        bandwidth_down_mbps=float(www.get("xput_down", 0)) or None,
        status=status,
        last_tested=last_tested,
    ).model_dump()


def _site_to_health_summary(site: dict[str, Any]) -> SiteHealthSummary:
    """Map a raw /v1/sites entry to a SiteHealthSummary."""
    counts = (site.get("statistics") or {}).get("counts", {})
    percentages = (site.get("statistics") or {}).get("percentages", {})
    total = counts.get("totalDevice", 0)
    offline = counts.get("offlineDevice", 0)
    clients = counts.get("wifiClient", 0) + counts.get("wiredClient", 0)

    status: SiteStatus
    if counts.get("offlineGatewayDevice", 0) > 0:
        status = "down"
    elif offline > 0:
        status = "degraded"
    else:
        status = "healthy"

    return SiteHealthSummary(
        site_id=site.get("siteId", ""),
        site_name=(site.get("meta") or {}).get("desc") or (site.get("meta") or {}).get("name", ""),
        status=status,
        devices_online=total - offline,
        devices_total=total,
        clients_active=clients,
        uptime_percentage=percentages.get("wanUptime", 0.0),
        last_updated=datetime.now(timezone.utc).isoformat(),
    )


def _normalize_site_identifier(value: str) -> str:
    """Normalize site identifiers for case-insensitive matching."""
    return value.strip().lower()


def _site_matches_identifier(site: dict[str, Any], site_identifier: str) -> bool:
    """Return True when a Site Manager site matches the provided identifier."""
    meta = site.get("meta") or {}
    values = [
        site.get("siteId"),
        site.get("id"),
        site.get("_id"),
        site.get("name"),
        site.get("desc"),
        site.get("internalReference"),
        meta.get("name") if isinstance(meta, dict) else None,
        meta.get("desc") if isinstance(meta, dict) else None,
    ]

    needle = _normalize_site_identifier(site_identifier)
    for value in values:
        if isinstance(value, str) and value and _normalize_site_identifier(value) == needle:
            return True
    return False


def _coerce_health_summary(health_data: dict[str, Any]) -> SiteHealthSummary:
    """Coerce either normalized or raw /v1/sites payload into SiteHealthSummary."""
    normalized_keys = {"site_id", "site_name", "status", "last_updated"}
    if normalized_keys.issubset(health_data.keys()):
        return SiteHealthSummary(**health_data)
    return _site_to_health_summary(health_data)


async def _resolve_site_health_entry(
    client: SiteManagerClient,
    site_id: str,
) -> dict[str, Any]:
    """Resolve a specific site across Site Manager and Network identifier formats."""
    try:
        return await client.get_site_health(site_id)
    except ResourceNotFoundError:
        pass

    candidate_identifiers = [site_id]

    network_client = get_network_client()
    if not network_client.is_authenticated:
        await network_client.authenticate()

    resolved_site = await network_client.resolve_site(site_id)
    candidate_identifiers.append(resolved_site.name)

    response = await client.get_site_health(None)
    sites = response.get("data", []) if isinstance(response, dict) else response
    if not isinstance(sites, list):
        raise ResourceNotFoundError("site", site_id)

    for entry in sites:
        if not isinstance(entry, dict):
            continue
        if any(_site_matches_identifier(entry, candidate) for candidate in candidate_identifiers):
            return entry

    raise ResourceNotFoundError("site", site_id)


def _site_to_inventory(site: dict[str, Any]) -> SiteInventory:
    """Map a raw /v1/sites entry to a SiteInventory."""
    counts = (site.get("statistics") or {}).get("counts", {})
    return SiteInventory(
        site_id=site.get("siteId", ""),
        site_name=(site.get("meta") or {}).get("desc") or (site.get("meta") or {}).get("name", ""),
        total_devices=counts.get("totalDevice", 0),
        wifi_devices=counts.get("wifiDevice", 0),
        wired_devices=counts.get("wiredDevice", 0),
        offline_devices=counts.get("offlineDevice", 0),
        total_clients=counts.get("wifiClient", 0) + counts.get("wiredClient", 0),
        wifi_clients=counts.get("wifiClient", 0),
        wired_clients=counts.get("wiredClient", 0),
        lan_configurations=counts.get("lanConfiguration", 0),
        wifi_configurations=counts.get("wifiConfiguration", 0),
        wan_configurations=counts.get("wanConfiguration", 0),
        last_updated=datetime.now(timezone.utc).isoformat(),
    )


@provider.tool()
async def get_site_health_summary(site_id: str | None = None) -> dict[str, Any]:
    """Get health summary for all sites or a specific site.

    Args:
        settings: Application settings
        site_id: Optional site identifier. If None, returns summary for all sites.

    Returns:
        Health summary
    """

    async with _site_manager_client_context() as client:
        logger.info(f"Retrieving site health summary (site_id={site_id})")

        if site_id:
            response = await _resolve_site_health_entry(client, site_id)
            return _site_to_health_summary(response).model_dump()

        response = await client.get_site_health(site_id)
        sites = response.get("data", [])
        return {"sites": [_site_to_health_summary(s).model_dump() for s in sites]}


@provider.tool()
async def get_cross_site_statistics() -> dict[str, Any]:
    """Get aggregate statistics across multiple sites.

    Args:
        settings: Application settings

    Returns:
        Cross-site statistics
    """

    async with _site_manager_client_context() as client:
        logger.info("Retrieving cross-site statistics")

        # Get all sites with health
        sites_response = await client.list_sites()
        sites_data = sites_response.get("data", sites_response.get("sites", []))

        health_response = await client.get_site_health()
        health_data = health_response.get("data", health_response)

        # Aggregate statistics
        total_sites = len(sites_data)
        sites_healthy = 0
        sites_degraded = 0
        sites_down = 0
        total_devices = 0
        devices_online = 0
        total_clients = 0
        total_bandwidth_up_mbps = 0.0
        total_bandwidth_down_mbps = 0.0

        site_summaries: list[SiteHealthSummary] = []
        if isinstance(health_data, list):
            for health in health_data:
                if not isinstance(health, dict):
                    continue

                summary = _coerce_health_summary(health)
                status = summary.status
                if status == "healthy":
                    sites_healthy += 1
                elif status == "degraded":
                    sites_degraded += 1
                elif status == "down":
                    sites_down += 1

                site_summaries.append(summary)
                total_devices += summary.devices_total
                devices_online += summary.devices_online
                total_clients += summary.clients_active

        return CrossSiteStatistics(
            total_sites=total_sites,
            sites_healthy=sites_healthy,
            sites_degraded=sites_degraded,
            sites_down=sites_down,
            total_devices=total_devices,
            devices_online=devices_online,
            total_clients=total_clients,
            total_bandwidth_up_mbps=total_bandwidth_up_mbps,
            total_bandwidth_down_mbps=total_bandwidth_down_mbps,
            site_summaries=site_summaries,
        ).model_dump()


@provider.tool()
async def get_site_inventory(site_id: str | None = None) -> dict[str, Any]:
    """Get inventory for a site or all sites from Site Manager statistics.

    Provides breakdown of devices, clients, and network configurations
    from the /v1/sites statistics data.

    Args:
        settings: Application settings
        site_id: Optional site identifier (UUID). If None, returns inventory for all sites.

    Returns:
        Site inventory dict, or dict with "sites" key containing list of inventories
    """

    async with _site_manager_client_context() as client:
        logger.info(f"Retrieving site inventory (site_id={site_id})")

        if site_id:
            site = await _resolve_site_health_entry(client, site_id)
            return _site_to_inventory(site).model_dump()
        else:
            response = await client.list_sites()
            sites = response.get("data", [])
            return {"sites": [_site_to_inventory(s).model_dump() for s in sites]}


@provider.tool()
async def compare_site_performance() -> dict[str, Any]:
    """Compare performance metrics across all sites.

    Analyzes uptime, latency, bandwidth, and health status to identify
    best and worst performing sites.

    Args:
        settings: Application settings

    Returns:
        Performance comparison with rankings and metrics
    """

    async with _site_manager_client_context() as client:
        logger.info("Comparing performance across sites")

        # Get site health data from /v1/sites (the only reliable cloud endpoint)
        health_response = await client.get_site_health()
        health_data = health_response.get("data", health_response)

        site_metrics: list[SitePerformanceMetrics] = []

        if isinstance(health_data, list):
            for raw_site in health_data:
                summary = _site_to_health_summary(raw_site)

                devices_total = summary.devices_total
                devices_online = summary.devices_online
                device_online_pct = (
                    (devices_online / devices_total * 100) if devices_total > 0 else 0.0
                )

                metrics = SitePerformanceMetrics(
                    site_id=summary.site_id,
                    site_name=summary.site_name,
                    uptime_percentage=summary.uptime_percentage,
                    device_online_percentage=device_online_pct,
                    client_count=summary.clients_active,
                    health_status=summary.status,
                )
                site_metrics.append(metrics)

        best_site = None
        worst_site = None

        if site_metrics:
            sorted_sites = sorted(
                site_metrics,
                key=lambda s: (s.uptime_percentage, s.device_online_percentage),
                reverse=True,
            )
            best_site = sorted_sites[0]
            worst_site = sorted_sites[-1]

        avg_uptime = (
            sum(m.uptime_percentage for m in site_metrics) / len(site_metrics)
            if site_metrics
            else 0.0
        )

        comparison = CrossSitePerformanceComparison(
            total_sites=len(site_metrics),
            best_performing_site=best_site,
            worst_performing_site=worst_site,
            average_uptime=avg_uptime,
            site_metrics=site_metrics,
        )

        return comparison.model_dump()


@provider.tool()
async def search_across_sites(
    query: str,
    search_type: str = "all",
) -> dict[str, Any]:
    """Search for devices across all sites using the Site Manager /v1/devices endpoint.

    Only device search is supported — client and network search requires the local
    Network API (use per-site tools instead).

    Args:
        settings: Application settings
        query: Search query (device name, MAC address, or model)
        search_type: "device" or "all" (both search devices only)

    Returns:
        Search results with host context
    """

    if search_type in ["client", "network"]:
        raise ValueError(
            "Client and network search requires the local Network API. "
            "Use per-site tools instead."
        )
    if search_type not in ["device", "all"]:
        raise ValueError(f"search_type must be one of ['device', 'all'], got '{search_type}'")

    async with _site_manager_client_context() as client:
        logger.info(f"Searching across sites: query='{query}', type={search_type}")

        response = await client.list_devices()
        hosts = response.get("data", [])

        results: list[dict[str, Any]] = []
        query_lower = query.lower()

        for host in hosts:
            host_id = host.get("hostId", "")
            host_name = host.get("hostName", host_id)

            for device in host.get("devices", []):
                name = device.get("name", "").lower()
                mac = device.get("mac", "").lower()
                model = device.get("model", "").lower()
                if query_lower in name or query_lower in mac or query_lower in model:
                    results.append(
                        {
                            "type": "device",
                            "host_id": host_id,
                            "host_name": host_name,
                            "resource": device,
                        }
                    )

        return CrossSiteSearchResult(
            total_results=len(results),
            search_query=query,
            result_type="device",
            results=results,
        ).model_dump()


# ISP Metrics Tools
@provider.tool()
async def get_isp_metrics(
    metric_type: str = "5m",
    duration: str | None = "24h",
    begin_timestamp: str | None = None,
    end_timestamp: str | None = None,
) -> dict[str, Any]:
    """Get ISP metrics by interval from the Site Manager API.

    Args:
        settings: Application settings
        metric_type: Interval type — "5m" (5-min intervals, 24h retention) or
                     "1h" (1-hour intervals, 30d retention)
        duration: Time window shorthand ("24h", "7d", "30d"). Cannot combine with timestamps.
        begin_timestamp: Start of range in RFC3339 format. Cannot combine with duration.
        end_timestamp: End of range in RFC3339 format. Cannot combine with duration.

    Returns:
        Raw ISP metrics response with nested periods data
    """
    async with _site_manager_client_context() as client:
        logger.info(f"Retrieving ISP metrics: type={metric_type}, duration={duration}")

        return await client.get_isp_metrics(
            metric_type,
            duration=duration,
            begin_timestamp=begin_timestamp,
            end_timestamp=end_timestamp,
        )


@provider.tool()
async def query_isp_metrics(
    metric_type: str = "5m",
    host_id: str = "",
    site_id: str = "",
    begin_timestamp: str | None = None,
    end_timestamp: str | None = None,
) -> dict[str, Any]:
    """Query ISP metrics for specific sites via POST.

    Args:
        settings: Application settings
        metric_type: Interval type — "5m" or "1h"
        host_id: Host identifier (required — get from list_hosts)
        site_id: Site identifier (required — get from list_hosts or list_all_sites_aggregated)
        begin_timestamp: Start of range in RFC3339 format
        end_timestamp: End of range in RFC3339 format

    Returns:
        Raw ISP metrics response with nested periods data
    """

    async with _site_manager_client_context() as client:
        logger.info(
            f"Querying ISP metrics (type={metric_type}, host_id={host_id}, site_id={site_id})"
        )

        site_entry: dict[str, Any] = {"hostId": host_id, "siteId": site_id}
        if begin_timestamp:
            site_entry["beginTimestamp"] = begin_timestamp
        if end_timestamp:
            site_entry["endTimestamp"] = end_timestamp

        body = {"sites": [site_entry]}
        return await client.query_isp_metrics(metric_type, body=body)


# SD-WAN Configuration Tools
@provider.tool()
async def list_sdwan_configs() -> list[dict[str, Any]]:
    """List all SD-WAN configurations.

    Args:
        settings: Application settings

    Returns:
        List of SD-WAN configurations
    """

    async with _site_manager_client_context() as client:
        logger.info("Retrieving SD-WAN configurations")

        response = await client.list_sdwan_configs()
        data = response.get("data", response.get("configs", []))

        if isinstance(data, list):
            return [SDWANConfig.model_validate(config).model_dump() for config in data]
        else:
            return []


@provider.tool()
async def get_sdwan_config(config_id: str) -> dict[str, Any]:
    """Get SD-WAN configuration by ID.

    Args:
        settings: Application settings
        config_id: Configuration identifier

    Returns:
        SD-WAN configuration details
    """

    async with _site_manager_client_context() as client:
        logger.info(f"Retrieving SD-WAN configuration: {config_id}")

        response = await client.get_sdwan_config(config_id)
        data = response.get("data", response)

        return SDWANConfig.model_validate(data).model_dump()


@provider.tool()
async def get_sdwan_config_status(config_id: str) -> dict[str, Any]:
    """Get SD-WAN configuration deployment status.

    Args:
        settings: Application settings
        config_id: Configuration identifier

    Returns:
        SD-WAN configuration deployment status
    """

    async with _site_manager_client_context() as client:
        logger.info(f"Retrieving SD-WAN configuration status: {config_id}")

        response = await client.get_sdwan_config_status(config_id)
        data = response.get("data", response)

        return SDWANConfigStatus.model_validate(data).model_dump()


# Host Management Tools
@provider.tool()
async def list_hosts(limit: int | None = None, offset: int | None = None) -> list[dict[str, Any]]:
    """List all managed hosts/consoles.

    Args:
        settings: Application settings
        limit: Optional maximum number of hosts to return
        offset: Optional number of hosts to skip (for pagination)

    Returns:
        List of managed hosts
    """

    async with _site_manager_client_context() as client:
        logger.info(f"Retrieving hosts list (limit={limit}, offset={offset})")

        response = await client.list_hosts(limit, offset)
        data = response.get("data", response.get("hosts", []))

        if isinstance(data, list):
            return [Host.model_validate(host).model_dump() for host in data]
        else:
            return []


@provider.tool()
async def get_host(host_id: str) -> dict[str, Any]:
    """Get host details by ID.

    Args:
        settings: Application settings
        host_id: Host identifier

    Returns:
        Host details
    """

    async with _site_manager_client_context() as client:
        logger.info(f"Retrieving host details: {host_id}")

        response = await client.get_host(host_id)
        data = response.get("data", response)

        return Host.model_validate(data).model_dump()

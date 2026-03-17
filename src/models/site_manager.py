"""Site Manager API models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SiteHealthSummary(BaseModel):
    """Health status for a site."""

    site_id: str = Field(..., description="Site identifier")
    site_name: str = Field(..., description="Site name")
    status: Literal["healthy", "degraded", "down"] = Field(..., description="Health status")
    devices_online: int = Field(0, description="Number of online devices")
    devices_total: int = Field(0, description="Total number of devices")
    clients_active: int = Field(0, description="Number of active clients")
    uptime_percentage: float = Field(0.0, description="Uptime percentage")
    last_updated: str = Field(..., description="Last update timestamp (ISO)")


class InternetHealthMetrics(BaseModel):
    """Internet connectivity metrics."""

    site_id: str | None = Field(None, description="Site identifier (None for aggregate)")
    latency_ms: float | None = Field(None, description="Average latency in milliseconds")
    packet_loss_percent: float = Field(0.0, description="Packet loss percentage")
    jitter_ms: float | None = Field(None, description="Jitter in milliseconds")
    bandwidth_up_mbps: float | None = Field(None, description="Upload bandwidth in Mbps")
    bandwidth_down_mbps: float | None = Field(None, description="Download bandwidth in Mbps")
    status: Literal["healthy", "degraded", "down"] = Field(..., description="Health status")
    last_tested: str = Field(..., description="Last test timestamp (ISO)")


class CrossSiteStatistics(BaseModel):
    """Aggregated statistics across multiple sites."""

    total_sites: int = Field(0, description="Total number of sites")
    sites_healthy: int = Field(0, description="Number of healthy sites")
    sites_degraded: int = Field(0, description="Number of degraded sites")
    sites_down: int = Field(0, description="Number of down sites")
    total_devices: int = Field(0, description="Total number of devices")
    devices_online: int = Field(0, description="Total online devices")
    total_clients: int = Field(0, description="Total number of clients")
    total_bandwidth_up_mbps: float = Field(0.0, description="Total upload bandwidth")
    total_bandwidth_down_mbps: float = Field(0.0, description="Total download bandwidth")
    site_summaries: list[SiteHealthSummary] = Field(
        default_factory=list, description="Health summary for each site"
    )


class SiteInventory(BaseModel):
    """Inventory for a single site, derived from /v1/sites statistics."""

    site_id: str = Field(..., description="Site identifier")
    site_name: str = Field(..., description="Site name")
    total_devices: int = Field(0, description="Total number of devices")
    wifi_devices: int = Field(0, description="Number of WiFi devices")
    wired_devices: int = Field(0, description="Number of wired devices")
    offline_devices: int = Field(0, description="Number of offline devices")
    total_clients: int = Field(0, description="Total active clients")
    wifi_clients: int = Field(0, description="Number of WiFi clients")
    wired_clients: int = Field(0, description="Number of wired clients")
    lan_configurations: int = Field(0, description="Number of LAN configurations")
    wifi_configurations: int = Field(0, description="Number of WiFi configurations")
    wan_configurations: int = Field(0, description="Number of WAN configurations")
    last_updated: str = Field(..., description="Inventory timestamp (ISO)")


class SitePerformanceMetrics(BaseModel):
    """Performance metrics for a single site."""

    site_id: str = Field(..., description="Site identifier")
    site_name: str = Field(..., description="Site name")
    uptime_percentage: float = Field(0.0, description="Uptime percentage")
    device_online_percentage: float = Field(0.0, description="Percentage of devices online")
    client_count: int = Field(0, description="Active clients")
    health_status: Literal["healthy", "degraded", "down"] = Field(..., description="Overall status")


class CrossSitePerformanceComparison(BaseModel):
    """Performance comparison across multiple sites."""

    total_sites: int = Field(0, description="Number of sites compared")
    best_performing_site: SitePerformanceMetrics | None = Field(
        None, description="Site with best overall performance"
    )
    worst_performing_site: SitePerformanceMetrics | None = Field(
        None, description="Site with worst overall performance"
    )
    average_uptime: float = Field(0.0, description="Average uptime across all sites")
    site_metrics: list[SitePerformanceMetrics] = Field(
        default_factory=list, description="Metrics for each site"
    )


class CrossSiteSearchResult(BaseModel):
    """Search result from cross-site search."""

    total_results: int = Field(0, description="Total number of results found")
    search_query: str = Field(..., description="Original search query")
    result_type: str = Field(..., description="Type of results (device)")
    results: list[dict] = Field(
        default_factory=list, description="Search results with site context"
    )


class SDWANConfig(BaseModel):
    """SD-WAN configuration from Site Manager API."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    config_id: str = Field(..., alias="id", description="Configuration identifier")
    name: str | None = Field(None, description="Configuration name")
    topology_type: str | None = Field(None, description="SD-WAN topology type")
    hub_site_ids: list[str] = Field(default_factory=list, description="Hub site identifiers")
    spoke_site_ids: list[str] = Field(default_factory=list, description="Spoke site identifiers")
    failover_enabled: bool = Field(False, description="Failover configuration enabled")
    created_at: str | None = Field(None, description="Creation timestamp (ISO)")
    updated_at: str | None = Field(None, description="Last update timestamp (ISO)")
    status: str | None = Field(None, description="Configuration status")


class SDWANConfigStatus(BaseModel):
    """SD-WAN configuration deployment status."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    config_id: str = Field(..., alias="id", description="Configuration identifier")
    deployment_status: str | None = Field(None, description="Deployment status")
    sites_deployed: int = Field(0, description="Number of sites successfully deployed")
    sites_total: int = Field(0, description="Total number of sites in configuration")
    last_deployment_at: str | None = Field(None, description="Last deployment timestamp (ISO)")
    error_message: str | None = Field(None, description="Error message if deployment failed")


class Host(BaseModel):
    """Managed host/console from Site Manager API."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    host_id: str = Field(..., alias="id", description="Host identifier")
    hostname: str = Field("", alias="name", description="Hostname")
    ip_address: str | None = Field(None, alias="ipAddress", description="IP address")
    mac_address: str | None = Field(None, alias="macAddress", description="MAC address")
    hardware_id: str | None = Field(None, alias="hardwareId", description="Hardware identifier")
    type: str | None = Field(None, description="Device type")
    status: str = Field("unknown", description="Host status")
    last_seen: str = Field(
        "", alias="lastConnectionStateChange", description="Last connection state change (ISO)"
    )
    registration_time: str | None = Field(
        None, alias="registrationTime", description="Registration timestamp (ISO)"
    )

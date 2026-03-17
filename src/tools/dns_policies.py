"""DNS policy management tools.

DNS policies in UniFi are DNS record overrides (A, CNAME, etc.)
for local DNS resolution on the gateway.
"""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..models.dns_policy import DNSPolicy
from ..utils import audit_action, get_logger, validate_confirmation

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = [
    "provider",
    "list_dns_policies",
    "get_dns_policy",
    "create_dns_policy",
    "update_dns_policy",
    "delete_dns_policy",
]


@provider.tool()
async def list_dns_policies(
    site_id: str,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict]:
    """List all DNS policies (record overrides) for a site.

    Args:
        site_id: Site identifier
        settings: Application settings
        limit: Maximum number of results
        offset: Starting position

    Returns:
        List of DNS policies
    """
    client = get_network_client()
    logger.info(f"Listing DNS policies for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    params: dict[str, Any] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset

    response = await client.get(client.integration_path(site.uuid, "dns/policies"), params=params)
    data = response if isinstance(response, list) else response.get("data", [])

    return [DNSPolicy(**policy).model_dump() for policy in data]


@provider.tool()
async def get_dns_policy(
    site_id: str,
    policy_id: str,
) -> dict:
    """Get details for a specific DNS policy.

    Args:
        site_id: Site identifier
        policy_id: DNS policy identifier
        settings: Application settings

    Returns:
        DNS policy details
    """
    client = get_network_client()
    logger.info(f"Getting DNS policy {policy_id} for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    response = await client.get(client.integration_path(site.uuid, f"dns/policies/{policy_id}"))
    data = response.get("data", response) if isinstance(response, dict) else response

    return DNSPolicy(**data).model_dump()


@provider.tool(annotations={"destructiveHint": True})
async def create_dns_policy(
    site_id: str,
    record_type: str,
    domain: str,
    enabled: bool = True,
    ipv4_address: str | None = None,
    ipv6_address: str | None = None,
    target: str | None = None,
    ttl_seconds: int = 0,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict:
    """Create a new DNS policy (record override).

    Args:
        site_id: Site identifier
        record_type: DNS record type (A_RECORD, AAAA_RECORD, CNAME, etc.)
        domain: Domain name for the record
        settings: Application settings
        enabled: Whether the policy is active
        ipv4_address: IPv4 address (for A_RECORD)
        ipv6_address: IPv6 address (for AAAA_RECORD)
        target: Target hostname (for CNAME)
        ttl_seconds: TTL in seconds (0 = default)
        confirm: Confirmation flag (required)
        dry_run: If True, validate but don't execute

    Returns:
        Created DNS policy
    """
    validate_confirmation(confirm, "create DNS policy", dry_run)

    client = get_network_client()
    logger.info(f"Creating DNS policy for {domain} ({record_type}) in site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    payload: dict[str, Any] = {
        "type": record_type,
        "domain": domain,
        "enabled": enabled,
        "ttlSeconds": ttl_seconds,
    }

    if ipv4_address is not None:
        payload["ipv4Address"] = ipv4_address
    if ipv6_address is not None:
        payload["ipv6Address"] = ipv6_address
    if target is not None:
        payload["target"] = target

    if dry_run:
        logger.info(f"[DRY RUN] Would create DNS policy with payload: {payload}")
        return {"dry_run": True, "payload": payload}

    response = await client.post(
        client.integration_path(site.uuid, "dns/policies"), json_data=payload
    )
    data = response.get("data", response) if isinstance(response, dict) else response

    await audit_action(
        client.settings,
        action_type="create_dns_policy",
        resource_type="dns_policy",
        resource_id=data.get("_id", data.get("id", "unknown")),
        site_id=site_id,
        details={"domain": domain, "type": record_type},
    )

    return DNSPolicy(**data).model_dump()


@provider.tool(annotations={"destructiveHint": True})
async def update_dns_policy(
    site_id: str,
    policy_id: str,
    record_type: str | None = None,
    domain: str | None = None,
    enabled: bool | None = None,
    ipv4_address: str | None = None,
    ipv6_address: str | None = None,
    target: str | None = None,
    ttl_seconds: int | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict:
    """Update an existing DNS policy (record override).

    Args:
        site_id: Site identifier
        policy_id: DNS policy identifier
        settings: Application settings
        record_type: DNS record type
        domain: Domain name
        enabled: Whether the policy is active
        ipv4_address: IPv4 address (for A_RECORD)
        ipv6_address: IPv6 address (for AAAA_RECORD)
        target: Target hostname (for CNAME)
        ttl_seconds: TTL in seconds
        confirm: Confirmation flag (required)
        dry_run: If True, validate but don't execute

    Returns:
        Updated DNS policy
    """
    validate_confirmation(confirm, "update DNS policy", dry_run)

    client = get_network_client()
    logger.info(f"Updating DNS policy {policy_id} for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    payload: dict[str, Any] = {}
    if record_type is not None:
        payload["type"] = record_type
    if domain is not None:
        payload["domain"] = domain
    if enabled is not None:
        payload["enabled"] = enabled
    if ipv4_address is not None:
        payload["ipv4Address"] = ipv4_address
    if ipv6_address is not None:
        payload["ipv6Address"] = ipv6_address
    if target is not None:
        payload["target"] = target
    if ttl_seconds is not None:
        payload["ttlSeconds"] = ttl_seconds

    if dry_run:
        logger.info(f"[DRY RUN] Would update DNS policy with payload: {payload}")
        return {"dry_run": True, "payload": payload}

    response = await client.put(
        client.integration_path(site.uuid, f"dns/policies/{policy_id}"),
        json_data=payload,
    )
    data = response.get("data", response) if isinstance(response, dict) else response

    await audit_action(
        client.settings,
        action_type="update_dns_policy",
        resource_type="dns_policy",
        resource_id=policy_id,
        site_id=site_id,
        details=payload,
    )

    return DNSPolicy(**data).model_dump()


@provider.tool(annotations={"destructiveHint": True})
async def delete_dns_policy(
    site_id: str,
    policy_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict:
    """Delete a DNS policy (record override).

    Args:
        site_id: Site identifier
        policy_id: DNS policy identifier
        settings: Application settings
        confirm: Confirmation flag (required)
        dry_run: If True, validate but don't execute

    Returns:
        Deletion status
    """
    validate_confirmation(confirm, "delete DNS policy", dry_run)

    client = get_network_client()
    logger.info(f"Deleting DNS policy {policy_id} for site {site_id}")

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)

    if dry_run:
        logger.info(f"[DRY RUN] Would delete DNS policy {policy_id}")
        return {"dry_run": True, "policy_id": policy_id}

    await client.delete(client.integration_path(site.uuid, f"dns/policies/{policy_id}"))

    await audit_action(
        client.settings,
        action_type="delete_dns_policy",
        resource_type="dns_policy",
        resource_id=policy_id,
        site_id=site_id,
        details={},
    )

    return {"success": True, "message": f"DNS policy {policy_id} deleted successfully"}

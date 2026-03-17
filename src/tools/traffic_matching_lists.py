"""Traffic Matching List management MCP tools."""

from typing import Any

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..models.traffic_matching_list import (
    TrafficMatchingList,
    TrafficMatchingListCreate,
    TrafficMatchingListType,
)
from ..utils import (
    ResourceNotFoundError,
    ValidationError,
    get_logger,
    log_audit,
    validate_confirmation,
    validate_limit_offset,
    validate_site_id,
)

logger = get_logger(__name__)
provider = LocalProvider()

__all__ = [
    "provider",
    "list_traffic_matching_lists",
    "get_traffic_matching_list",
    "create_traffic_matching_list",
    "update_traffic_matching_list",
    "delete_traffic_matching_list",
]


@provider.tool()
async def list_traffic_matching_lists(
    site_id: str,
    limit: int | None = None,
    offset: int | None = None,
) -> list[dict[str, Any]]:
    """List all traffic matching lists in a site (read-only).

    Args:
        site_id: Site identifier
        settings: Application settings
        limit: Maximum number of lists to return
        offset: Number of lists to skip

    Returns:
        List of traffic matching list dictionaries
    """
    site_id = validate_site_id(site_id)
    limit, offset = validate_limit_offset(limit, offset)
    client = get_network_client()

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    endpoint = client.integration_path(site.uuid, "traffic-matching-lists")
    response = await client.get(endpoint)
    lists_data: list[dict[str, Any]] = (
        response if isinstance(response, list) else response.get("data", [])
    )

    paginated = lists_data[offset : offset + limit]
    logger.info(f"Retrieved {len(paginated)} traffic matching lists for site '{site_id}'")
    return [TrafficMatchingList(**lst).model_dump() for lst in paginated]


@provider.tool()
async def get_traffic_matching_list(
    site_id: str,
    list_id: str,
) -> dict[str, Any]:
    """Get details for a specific traffic matching list.

    Args:
        site_id: Site identifier
        list_id: Traffic matching list ID
        settings: Application settings

    Returns:
        Traffic matching list dictionary

    Raises:
        ResourceNotFoundError: If list not found
    """
    site_id = validate_site_id(site_id)
    client = get_network_client()

    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    endpoint = client.integration_path(site.uuid, f"traffic-matching-lists/{list_id}")
    response = await client.get(endpoint)

    if isinstance(response, dict) and "data" in response:
        list_data = response["data"]
    else:
        list_data = response

    if not list_data:
        raise ResourceNotFoundError("traffic_matching_list", list_id)

    logger.info(f"Retrieved traffic matching list {list_id}")
    return TrafficMatchingList(**list_data).model_dump()


@provider.tool(annotations={"destructiveHint": True})
async def create_traffic_matching_list(
    site_id: str,
    list_type: str,
    name: str,
    items: list[str],
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Create a new traffic matching list.

    Args:
        site_id: Site identifier
        list_type: List type (PORTS, IPV4_ADDRESSES, IPV6_ADDRESSES)
        name: List name
        items: List items (ports, IPs, etc.)
        settings: Application settings
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't create

    Returns:
        Created list dictionary or dry-run result

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ValidationError: If validation fails
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "traffic matching list operation", dry_run)
    client = get_network_client()

    # Validate list type
    valid_types = ["PORTS", "IPV4_ADDRESSES", "IPV6_ADDRESSES"]
    if list_type not in valid_types:
        raise ValidationError(f"Invalid list type '{list_type}'. Must be one of: {valid_types}")

    # Validate items not empty
    if not items or len(items) == 0:
        raise ValidationError("Items list cannot be empty")

    # Build list data
    create_data = TrafficMatchingListCreate(
        type=TrafficMatchingListType(list_type),
        name=name,
        items=items,
    )

    parameters = {
        "site_id": site_id,
        "type": list_type,
        "name": name,
        "items_count": len(items),
    }

    if dry_run:
        logger.info(f"DRY RUN: Would create traffic matching list '{name}' in site '{site_id}'")
        await log_audit(
            operation="create_traffic_matching_list",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_create": create_data.model_dump()}

    try:
        site = await client.resolve_site(site_id)
        endpoint = client.integration_path(site.uuid, "traffic-matching-lists")
        response = await client.post(endpoint, json_data=create_data.model_dump())
        created_raw: Any = (
            response if isinstance(response, list) else response.get("data", response)
        )
        created_list = created_raw if isinstance(created_raw, dict) else {}

        logger.info(f"Created traffic matching list '{name}' in site '{site_id}'")
        await log_audit(
            operation="create_traffic_matching_list",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return created_list

    except Exception as e:
        logger.error(f"Failed to create traffic matching list '{name}': {e}")
        await log_audit(
            operation="create_traffic_matching_list",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def update_traffic_matching_list(
    site_id: str,
    list_id: str,
    list_type: str | None = None,
    name: str | None = None,
    items: list[str] | None = None,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Update an existing traffic matching list.

    Args:
        site_id: Site identifier
        list_id: Traffic matching list ID
        settings: Application settings
        list_type: New list type
        name: New list name
        items: New list items
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't update

    Returns:
        Updated list dictionary or dry-run result

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If list not found
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "traffic matching list operation", dry_run)
    client = get_network_client()

    # Validate list type if provided
    if list_type is not None:
        valid_types = ["PORTS", "IPV4_ADDRESSES", "IPV6_ADDRESSES"]
        if list_type not in valid_types:
            raise ValidationError(f"Invalid list type '{list_type}'. Must be one of: {valid_types}")

    # Validate items if provided
    if items is not None and len(items) == 0:
        raise ValidationError("Items list cannot be empty")

    parameters = {
        "site_id": site_id,
        "list_id": list_id,
        "type": list_type,
        "name": name,
        "items_count": len(items) if items else None,
    }

    if dry_run:
        logger.info(f"DRY RUN: Would update traffic matching list '{list_id}' in site '{site_id}'")
        await log_audit(
            operation="update_traffic_matching_list",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_update": parameters}

    try:
        site = await client.resolve_site(site_id)

        endpoint = client.integration_path(site.uuid, f"traffic-matching-lists/{list_id}")
        response = await client.get(endpoint)
        existing_raw: Any = (
            response if isinstance(response, list) else response.get("data", response)
        )
        existing_list = existing_raw if isinstance(existing_raw, dict) else None

        if not existing_list:
            raise ResourceNotFoundError("traffic_matching_list", list_id)

        update_data: dict[str, Any] = existing_list.copy()
        if list_type is not None:
            update_data["type"] = list_type
        if name is not None:
            update_data["name"] = name
        if items is not None:
            update_data["items"] = items

        response = await client.put(
            endpoint,
            json_data=update_data,
        )
        updated_raw: Any = (
            response if isinstance(response, list) else response.get("data", response)
        )
        updated_list = updated_raw if isinstance(updated_raw, dict) else {}

        logger.info(f"Updated traffic matching list '{list_id}' in site '{site_id}'")
        await log_audit(
            operation="update_traffic_matching_list",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return updated_list

    except Exception as e:
        logger.error(f"Failed to update traffic matching list '{list_id}': {e}")
        await log_audit(
            operation="update_traffic_matching_list",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise


@provider.tool(annotations={"destructiveHint": True})
async def delete_traffic_matching_list(
    site_id: str,
    list_id: str,
    confirm: bool | str = False,
    dry_run: bool | str = False,
) -> dict[str, Any]:
    """Delete a traffic matching list.

    Args:
        site_id: Site identifier
        list_id: Traffic matching list ID
        settings: Application settings
        confirm: Confirmation flag (must be True to execute)
        dry_run: If True, validate but don't delete

    Returns:
        Deletion result dictionary

    Raises:
        ConfirmationRequiredError: If confirm is not True
        ResourceNotFoundError: If list not found
    """
    site_id = validate_site_id(site_id)
    validate_confirmation(confirm, "traffic matching list operation", dry_run)
    client = get_network_client()

    parameters = {"site_id": site_id, "list_id": list_id}

    if dry_run:
        logger.info(
            f"DRY RUN: Would delete traffic matching list '{list_id}' from site '{site_id}'"
        )
        await log_audit(
            operation="delete_traffic_matching_list",
            parameters=parameters,
            result="dry_run",
            site_id=site_id,
            dry_run=True,
        )
        return {"dry_run": True, "would_delete": list_id}

    try:
        site = await client.resolve_site(site_id)

        endpoint = client.integration_path(site.uuid, f"traffic-matching-lists/{list_id}")
        try:
            await client.get(endpoint)
        except Exception as err:
            raise ResourceNotFoundError("traffic_matching_list", list_id) from err

        await client.delete(endpoint)

        logger.info(f"Deleted traffic matching list '{list_id}' from site '{site_id}'")
        await log_audit(
            operation="delete_traffic_matching_list",
            parameters=parameters,
            result="success",
            site_id=site_id,
        )

        return {"success": True, "deleted_list_id": list_id}

    except Exception as e:
        logger.error(f"Failed to delete traffic matching list '{list_id}': {e}")
        await log_audit(
            operation="delete_traffic_matching_list",
            parameters=parameters,
            result="failed",
            site_id=site_id,
        )
        raise

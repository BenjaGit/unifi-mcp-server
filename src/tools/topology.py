"""Network topology tools for UniFi MCP Server."""

import json
from datetime import datetime, timezone
from typing import Any, Literal

from fastmcp.server.providers import LocalProvider

from ..api.pool import get_network_client
from ..models.topology import NetworkDiagram, TopologyConnection, TopologyNode
from ..utils.exceptions import ValidationError

provider = LocalProvider()

__all__ = [
    "provider",
    "get_network_topology",
    "get_device_connections",
    "get_port_mappings",
    "export_topology",
    "get_topology_statistics",
]


@provider.tool()
async def get_network_topology(site_id: str, include_coordinates: bool = False) -> dict[str, Any]:
    """Retrieve complete network topology graph."""
    client = get_network_client()
    if not client.is_authenticated:
        await client.authenticate()

    site = await client.resolve_site(site_id)
    devices_endpoint = client.integration_path(site.uuid, "devices")
    clients_endpoint = client.integration_path(site.uuid, "clients")

    device_nodes: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = await client.get(f"{devices_endpoint}?offset={offset}&limit=100")
        data = response if isinstance(response, list) else response.get("data", [])
        if not data:
            break
        device_nodes.extend(data)
        offset += len(data)
        if len(data) < 100:
            break

    client_nodes: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = await client.get(f"{clients_endpoint}?offset={offset}&limit=100")
        data = response if isinstance(response, list) else response.get("data", [])
        if not data:
            break
        client_nodes.extend(data)
        offset += len(data)
        if len(data) < 100:
            break

    nodes: list[TopologyNode] = []
    connections: list[TopologyConnection] = []
    depth_map: dict[str, int] = {}

    for device in device_nodes:
        device_id = device.get("id", "")
        uplink_info = device.get("uplink", {})
        uplink_device_id = uplink_info.get("deviceId")

        if uplink_device_id:
            parent_depth = depth_map.get(uplink_device_id, 0)
            depth_map[device_id] = parent_depth + 1
        else:
            depth_map[device_id] = 0

        node = TopologyNode(
            node_id=device_id,
            node_type="device",
            name=device.get("name"),
            mac=device.get("macAddress"),
            ip=device.get("ipAddress"),
            model=device.get("model"),
            type_detail=device.get("model"),
            uplink_device_id=uplink_device_id,
            uplink_port=uplink_info.get("portIndex"),
            uplink_depth=depth_map.get(device_id, 0),
            state=1 if device.get("state") == "CONNECTED" else 0,
            adopted=True,
            x_coordinate=None,
            y_coordinate=None,
        )
        nodes.append(node)

        if uplink_device_id:
            connections.append(
                TopologyConnection(
                    connection_id=f"conn_{device_id}_uplink",
                    source_node_id=device_id,
                    target_node_id=uplink_device_id,
                    connection_type="uplink",
                    source_port=uplink_info.get("portIndex"),
                    target_port=None,
                    port_name=None,
                    speed_mbps=uplink_info.get("speedMbps"),
                    duplex=None,
                    link_quality=None,
                    is_uplink=True,
                    status="up" if device.get("state") == "CONNECTED" else "down",
                )
            )

    for client_data in client_nodes:
        client_id = client_data.get("id", "")
        client_type = client_data.get("type", "WIRED")
        uplink_device_id = client_data.get("uplinkDeviceId")

        nodes.append(
            TopologyNode(
                node_id=client_id,
                node_type="client",
                name=client_data.get("name"),
                mac=client_data.get("macAddress"),
                ip=client_data.get("ipAddress"),
                model=None,
                type_detail=None,
                uplink_device_id=uplink_device_id,
                uplink_port=None,
                uplink_depth=None,
                state=1,
                adopted=None,
                x_coordinate=None,
                y_coordinate=None,
            )
        )

        if uplink_device_id:
            conn_type = "wired" if client_type == "WIRED" else "wireless"
            connections.append(
                TopologyConnection(
                    connection_id=f"conn_client_{client_id}",
                    source_node_id=client_id,
                    target_node_id=uplink_device_id,
                    connection_type=conn_type,
                    source_port=client_data.get("portIdx"),
                    target_port=None,
                    port_name=None,
                    speed_mbps=None,
                    duplex=None,
                    link_quality=None,
                    is_uplink=False,
                    status="up",
                )
            )

    total_devices = len([n for n in nodes if n.node_type == "device"])
    total_clients = len([n for n in nodes if n.node_type == "client"])
    max_depth = max([n.uplink_depth for n in nodes if n.uplink_depth is not None], default=0)

    diagram = NetworkDiagram(
        site_id=site.uuid,
        site_name=site.name,
        generated_at=datetime.now(timezone.utc).isoformat(),
        nodes=nodes,
        connections=connections,
        total_devices=total_devices,
        total_clients=total_clients,
        total_connections=len(connections),
        max_depth=max_depth,
        layout_algorithm=None,
        has_coordinates=include_coordinates,
    )

    return diagram.model_dump()


@provider.tool()
async def get_device_connections(site_id: str, device_id: str | None) -> list[dict[str, Any]]:
    """Get device interconnection details."""
    topology = await get_network_topology(site_id)
    raw_connections = topology.get("connections", [])
    connections: list[dict[str, Any]] = raw_connections if isinstance(raw_connections, list) else []
    if device_id:
        connections = [
            conn
            for conn in connections
            if conn.get("source_node_id") == device_id or conn.get("target_node_id") == device_id
        ]
    return connections


@provider.tool()
async def get_port_mappings(site_id: str, device_id: str) -> dict[str, Any]:
    """Get port-level connection mappings for a device."""
    topology = await get_network_topology(site_id)
    connections = topology.get("connections", [])

    port_map: dict[int, dict[str, Any]] = {}
    for conn in connections:
        if conn.get("source_node_id") == device_id:
            port_num = conn.get("source_port")
            if port_num is not None:
                port_map[port_num] = {
                    "connected_to": conn.get("target_node_id"),
                    "connection_type": conn.get("connection_type"),
                    "speed_mbps": conn.get("speed_mbps"),
                    "status": conn.get("status"),
                }
        elif conn.get("target_node_id") == device_id:
            port_num = conn.get("target_port")
            if port_num is not None:
                port_map[port_num] = {
                    "connected_to": conn.get("source_node_id"),
                    "connection_type": conn.get("connection_type"),
                    "speed_mbps": conn.get("speed_mbps"),
                    "status": conn.get("status"),
                }

    return {"device_id": device_id, "ports": port_map}


@provider.tool()
async def export_topology(site_id: str, format: Literal["json", "graphml", "dot"]) -> str:
    """Export network topology in JSON, GraphML, or DOT format."""
    if format not in ["json", "graphml", "dot"]:
        raise ValidationError(
            f"Invalid export format: {format}. Must be 'json', 'graphml', or 'dot'"
        )

    topology = await get_network_topology(site_id)

    if format == "json":
        return json.dumps(topology, indent=2)

    if format == "graphml":
        nodes = topology.get("nodes", [])
        connections = topology.get("connections", [])

        graphml = ['<?xml version="1.0" encoding="UTF-8"?>']
        graphml.append('<graphml xmlns="http://graphml.graphdrawing.org/xmlns">')
        graphml.append('  <graph id="UniFi Network" edgedefault="directed">')
        for node in nodes:
            node_id = node.get("node_id", "")
            node_type = node.get("node_type", "")
            name = node.get("name", "")
            graphml.append(f'    <node id="{node_id}">')
            graphml.append(f'      <data key="type">{node_type}</data>')
            graphml.append(f'      <data key="name">{name}</data>')
            graphml.append("    </node>")

        for conn in connections:
            source = conn.get("source_node_id", "")
            target = conn.get("target_node_id", "")
            conn_type = conn.get("connection_type", "")
            graphml.append(f'    <edge source="{source}" target="{target}">')
            graphml.append(f'      <data key="type">{conn_type}</data>')
            graphml.append("    </edge>")

        graphml.append("  </graph>")
        graphml.append("</graphml>")
        return "\n".join(graphml)

    nodes = topology.get("nodes", [])
    connections = topology.get("connections", [])
    dot = ["digraph UniFiNetwork {"]
    dot.append("  node [shape=box];")
    for node in nodes:
        node_id = node.get("node_id", "")
        name = node.get("name", node_id)
        node_type = node.get("node_type", "")
        dot.append(f'  "{node_id}" [label="{name}\\n({node_type})"];')

    for conn in connections:
        source = conn.get("source_node_id", "")
        target = conn.get("target_node_id", "")
        conn_type = conn.get("connection_type", "")
        dot.append(f'  "{source}" -> "{target}" [label="{conn_type}"];')

    dot.append("}")
    return "\n".join(dot)


@provider.tool()
async def get_topology_statistics(site_id: str) -> dict[str, Any]:
    """Get network topology statistics."""
    topology = await get_network_topology(site_id)
    return {
        "site_id": topology.get("site_id"),
        "total_devices": topology.get("total_devices", 0),
        "total_clients": topology.get("total_clients", 0),
        "total_connections": topology.get("total_connections", 0),
        "max_depth": topology.get("max_depth", 0),
        "generated_at": topology.get("generated_at"),
    }

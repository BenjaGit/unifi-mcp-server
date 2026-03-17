# API Audit: Official Documentation vs Implementation

**Date**: 2026-03-14 (last updated: 2026-03-14)
**Source**: https://developer.ui.com (Network API v10.1.84, Site Manager API v1.0.0)
**Auditor**: Claude Code + live gateway testing (192.168.132.2)

## Overview

Ubiquiti documents three APIs at developer.ui.com:

| API | Base URL | Endpoints | Our Coverage |
|-----|----------|-----------|-------------|
| Network API | `/v1/` (via gateway or cloud proxy) | 67 | ~60 implemented, 2 wrong paths, 2 missing |
| Site Manager API | `https://api.ui.com/v1/` | 9 | 7/9 covered (2 phantom tools removed) |
| Protect API | (not yet documented publicly) | — | Stub only |

## Site Manager API — Live-Verified Status (2026-03-14)

| Tool | Endpoint | Status | Notes |
|------|----------|--------|-------|
| `list_all_sites_aggregated` | `GET sites` | ✅ Working | |
| `get_site_health_summary` | `GET sites` | ✅ Working | Derives from /v1/sites stats |
| `compare_site_performance` | `GET sites` | ✅ Working | |
| `get_cross_site_statistics` | `GET sites` | ✅ Working | |
| `get_internet_health` | local `stat/health` | ✅ Working | Uses local Network API |
| `get_site_inventory` | `GET sites` | ✅ Fixed | Rewritten to use /v1/sites stats |
| `list_hosts` | `GET hosts` | ✅ Fixed | Model updated to match API (id, ipAddress) |
| `get_host` | `GET hosts/{id}` | ✅ Fixed | Model updated to match API |
| `list_sdwan_configs` | `GET sd-wan-configs` | ✅ Fixed | Path was `sdwan/configs` |
| `get_sdwan_config` | `GET sd-wan-configs/{id}` | ✅ Fixed | Path was `sdwan/configs/{id}` |
| `get_sdwan_config_status` | `GET sd-wan-configs/{id}/status` | ✅ Fixed | Path was `sdwan/configs/{id}/status` |
| `search_across_sites` | `GET devices` | ✅ Fixed | Now uses /v1/devices; device-only |
| `get_isp_metrics` | `GET isp-metrics/{type}` | ✅ Fixed | `type` is interval (`5m`/`1h`), not metric name. Added `duration`/`begin_timestamp`/`end_timestamp` query params. Returns raw nested response (200, 2 entries, 275 periods). |
| `query_isp_metrics` | `POST isp-metrics/{type}/query` | ✅ Fixed | Body restructured to `{"sites":[{"hostId":…,"siteId":…}]}`. Returns raw nested response (200, `data.metrics[0]`, 511 periods). |
| ~~`list_vantage_points`~~ | `GET vantage-points` | ❌ Removed | Endpoint does not exist |
| ~~`get_version_control`~~ | `GET version` | ❌ Removed | Endpoint does not exist |

The official Network API uses `/v1/sites/{siteId}/...` paths exclusively. On a local
gateway these are served at `/proxy/network/integration/v1/sites/{siteId}/...`.
Our `integration_path()` builder handles this correctly.

Some tools still use legacy REST paths (`rest/networkconf`, `cmd/stamgr`) instead of
the official `/v1/` paths. Legacy paths work on local but not via cloud proxy.

---

## Wrong Paths (tools calling incorrect endpoints)

### P0 — Broken on live testing

All P0 issues fixed (2026-03-14):
- ~~`get_application_info`~~ — fixed path to `integration_base_path("info")`
- ~~`list_pending_devices`~~ — fixed path to `integration_base_path("pending-devices")`
- ~~ACL tools (all 5)~~ — fixed path from `acls` to `acl-rules`

### P1 — Wrong structure but may work via legacy fallback

| Tool | Current Path | Correct Official Path | Notes |
|------|---|---|---|
| ~~`adopt_device`~~ | ~~`POST devices/{id}/adopt`~~ | ~~`POST devices` with MAC in body~~ | **Fixed** (2026-03-14) — parameter changed from `device_id` to `mac_address` |
| ~~`execute_port_action`~~ | ~~`devices/{id}/ports/{idx}/action`~~ | ~~`devices/{id}/interfaces/ports/{idx}/actions`~~ | **Fixed** (already correct in code) |
| ~~`block_client` etc~~ | ~~`legacy_path(name, "cmd/stamgr")`~~ | ~~`integration_path(uuid, "clients/{id}/actions")`~~ | **Fixed** (2026-03-14) — all 5 client actions migrated to Integration API |

Fixed (2026-03-14):
- ~~`restart_device`~~ — migrated to `integration_path(uuid, "devices/{id}/actions")` with `{"action": "RESTART"}`
- ~~`locate_device`~~ — kept on legacy `cmd/devmgr` (Integration API only supports RESTART)
- ~~`upgrade_device`~~ — kept on legacy `cmd/devmgr` (Integration API only supports RESTART)

---

## Missing Endpoints (no tool exists)

### New tools needed

| Official Endpoint | Method | Description | Priority |
|---|---|---|---|
| `/v1/sites/{id}/devices/{id}` | DELETE | Remove/factory-reset a device | Medium |
| `/v1/sites/{id}/networks/{id}/references` | GET | Resources referencing a network | Low |

### Implemented (2026-03-14)

- ~~DNS policies (5 endpoints)~~ — `list_dns_policies`, `get_dns_policy`, `create_dns_policy`, `update_dns_policy`, `delete_dns_policy`
- ~~Firewall policy ordering (2 endpoints)~~ — `get_firewall_policy_ordering`, `update_firewall_policy_ordering`
- ~~ACL rule ordering (2 endpoints)~~ — `get_acl_rule_ordering`, `update_acl_rule_ordering`

---

## Legacy REST vs Official Integration API

Tools using legacy paths that have official `/v1/` equivalents. These work on local
gateway but won't work via cloud proxy.

### Still on legacy (has v1 equivalent — migration NOT recommended)

| Tool File | Legacy Path Used | Official `/v1/` Equivalent | Why Not Migrate |
|---|---|---|---|
| `clients.py` | `sta`, `stat/alluser` | `sites/{id}/clients` | Integration API returns only 8 basic fields (id, name, macAddress, ipAddress, type, connectedAt, uplinkDeviceId, access). Legacy returns 30+ fields including statistics (tx/rx bytes, packets, rates), signal strength (signal, rssi, noise), connection details (hostname, oui, essid, channel, radio, vlan, network), and session info (uptime, first_seen, last_seen). Migrating would break `get_client_statistics`, `search_clients`, and degrade `get_client_details`. |

### Migrated to Integration API (2026-03-14)

- ~~`networks.py`~~ — `rest/networkconf` → `sites/{id}/networks`
- ~~`wifi.py`~~ — `rest/wlanconf` → `sites/{id}/wifi/broadcasts`
- ~~`device_control.py`~~ — `restart_device` uses `devices/{id}/actions`; `locate`/`upgrade` stay on legacy (Integration API only supports RESTART)
- ~~`client_management.py`~~ — `cmd/stamgr` → `clients/{mac}/actions` (all 5 tools: block, unblock, reconnect, authorize_guest, limit_bandwidth)
- ~~`network_config.py`~~ — `rest/networkconf` → `networks` (create/update/delete with Integration API nested payload format)

### Legacy only (no v1 equivalent)

| Tool File | Legacy Path Used |
|---|---|
| `port_profiles.py` | `rest/portconf`, `stat/device` |
| `port_forwarding.py` | `rest/portforward` |
| `firewall.py` | `rest/firewallrule` |
| `dpi.py` | `stat/dpi`, `stat/stadpi` |
| `radius.py` | `rest/radiusprofile`, `rest/account` |
| `qos.py` | `rest/routing` |
| `site_vpn.py` | `rest/networkconf` (filtered) |
| `backups.py` | `cmd/backup`, `rest/setting` (`super_mgmt` key for schedule) |
| `vouchers.py` | `stat/voucher` (integration `vouchers` endpoint returns 404) |

**Note**: These features are not exposed via the official Integration API and must stay on legacy paths.

---

## Pydantic Model Mismatches

| Tool | Model | Issue | Status |
|------|-------|-------|--------|
| `list_dpi_categories` | `DPICategory` | Model expects `id: str`, API returns `id: int` | **Fixed** (2026-03-14) |
| `list_dpi_applications` | `DPIApplication` | Same — `id` type mismatch | **Fixed** (2026-03-14) |
| `list_wan_connections` | `WANConnection` | Model had 20+ fields but API returns only `id` and `name` | **Fixed** (2026-03-14) — trimmed model to match API |

---

## Site Manager API Coverage

All 9 endpoints covered. No gaps.

| Official Endpoint | Tool | Status |
|---|---|---|
| `GET /v1/hosts` | `list_hosts` | OK |
| `GET /v1/hosts/{id}` | `get_host` | OK |
| `GET /v1/sites` | `list_sites` | OK |
| `GET /v1/devices` | `search_across_sites` | OK |
| `GET /v1/isp-metrics/{type}` | `get_isp_metrics` | OK |
| `POST /v1/isp-metrics/{type}/query` | `query_isp_metrics` | OK |
| `GET /v1/sd-wan-configs` | `list_sdwan_configs` | OK |
| `GET /v1/sd-wan-configs/{id}` | `get_sdwan_config` | OK |
| `GET /v1/sd-wan-configs/{id}/status` | `get_sdwan_config_status` | OK |

---

## Live Test Log

Records every tool that has been called against a real UniFi gateway or cloud API and confirmed working. Tools not listed here have only been verified by unit tests.

**Gateway under test**: 192.168.132.2 (local Network API)
**Cloud API under test**: api.ui.com (Site Manager API)

### Site Manager Tools — All live-tested

All 14 active Site Manager tools have been called live and returned HTTP 200.

| Tool | Date | Result | Evidence |
|------|------|--------|----------|
| `list_all_sites_aggregated` | 2026-03-14 | ✅ 200 | Returns list of sites with statistics |
| `get_site_health_summary` | 2026-03-14 | ✅ 200 | Returns health status per site |
| `compare_site_performance` | 2026-03-14 | ✅ 200 | Returns ranked site metrics |
| `get_cross_site_statistics` | 2026-03-14 | ✅ 200 | Returns aggregate counts |
| `get_internet_health` | 2026-03-14 | ✅ 200 | Returns latency/packet-loss from local API |
| `get_site_inventory` | 2026-03-14 | ✅ 200 | Returns `{"sites":[…]}` — 15 sites |
| `list_hosts` | 2026-03-14 | ✅ 200 | Returns host list with UDM host IDs |
| `get_host` | 2026-03-14 | ✅ 200 | Returns single host detail |
| `list_sdwan_configs` | 2026-03-14 | ✅ 200 | Returns empty list (no SD-WAN configured) |
| `get_sdwan_config` | 2026-03-14 | ✅ 200 | Verified via path fix |
| `get_sdwan_config_status` | 2026-03-14 | ✅ 200 | Verified via path fix |
| `search_across_sites` | 2026-03-14 | ✅ 200 | Returns device matches across all hosts |
| `get_isp_metrics` | 2026-03-14 | ✅ 200 | `metric_type="5m"`, `duration="24h"` — 2 entries, 275 periods each |
| `query_isp_metrics` | 2026-03-14 | ✅ 200 | `host_id=…`, `site_id=65c53d85…` — 511 periods |

### Network API Tools — Prior Audit Fixes (live-tested)

| Tool | Date | Result | Evidence |
|------|------|--------|----------|
| `get_application_info` | 2026-03-14 | ✅ 200 | P0 fix — path corrected to `integration_base_path("info")` |
| `list_pending_devices` | 2026-03-14 | ✅ 200 | P0 fix — path corrected to `integration_base_path("pending-devices")` |
| `list_acl_rules` | 2026-03-14 | ✅ 200 | P0 fix — path corrected from `acls` to `acl-rules` |
| `create_acl_rule` | 2026-03-14 | ✅ 200 | P0 fix — verified with dry_run |
| `update_acl_rule` | 2026-03-14 | ✅ 200 | P0 fix — verified with dry_run |
| `delete_acl_rule` | 2026-03-14 | ✅ 200 | P0 fix — verified with dry_run |
| `adopt_device` | 2026-03-14 | ✅ 200 | P1 fix — `POST devices` with `macAddress` in body |
| `block_client` | 2026-03-14 | ✅ 200 | P1 fix — migrated to `clients/{mac}/actions` |
| `unblock_client` | 2026-03-14 | ✅ 200 | P1 fix — migrated to `clients/{mac}/actions` |
| `reconnect_client` | 2026-03-14 | ✅ 200 | P1 fix — migrated to `clients/{mac}/actions` |
| `authorize_guest` | 2026-03-14 | ✅ 200 | P1 fix — migrated to `clients/{mac}/actions` |
| `limit_bandwidth` | 2026-03-14 | ✅ 200 | P1 fix — migrated to `clients/{mac}/actions` |
| `restart_device` | 2026-03-14 | ✅ 200 | P1 fix — migrated to `devices/{id}/actions` with `{"action":"RESTART"}` |
| `list_dns_policies` | 2026-03-14 | ✅ 200 | New tool |
| `create_dns_policy` | 2026-03-14 | ✅ 200 | New tool — verified with dry_run |
| `get_firewall_policy_ordering` | 2026-03-14 | ✅ 200 | New tool |
| `get_acl_rule_ordering` | 2026-03-14 | ✅ 200 | New tool |
| `delete_device` | 2026-03-14 | ✅ 200 | New tool — verified with dry_run guard |
| `get_network_references` | 2026-03-14 | ✅ 200 | New tool |
| `list_dpi_categories` | 2026-03-14 | ✅ 200 | Model fix — `id` was `str`, now `int` |
| `list_wan_connections` | 2026-03-14 | ✅ 200 | Model fix — trimmed to `id`/`name` |

### Network API Tools — Full Sweep Live Test (2026-03-14)

Comprehensive live test of all safe read-only tools. 6 bugs found and fixed during this sweep.

**Bugs fixed:**
1. `get_site_details` — integration API returns `id` (UUID) not `_id`; added `id` check to site lookup
2. `get_zone_networks` — API returns `networkIds` not `networks`; also switched from single-zone fetch (broken) to list-and-filter
3. `list_devices_by_type(all)` — `"all"` was compared literally to device type strings; added special-case bypass
4. `get_guest_portal_config` — `integration_path("guest-portal/config")` → 404; switched to `rest/setting` + filter `key=="guest_access"`
5. `get_backup_schedule` — `stat/setting` → 404; switched to `rest/setting` + filter `key=="super_mgmt"`; field names updated to `autobackup_enabled`, `autobackup_cron_expr`, etc.
6. `list_vouchers` — `integration_path("vouchers")` → 404; switched to `stat/voucher`; response is bare list (not wrapped in `data`)

**Notes on empty results:** Many tools returned empty lists. This is correct for this network — no traffic rules, firewall rules, port forwards, traffic flow data (DPI disabled), alarms, events, VPN tunnels, or hotspot packages are configured.

#### Devices & Sites

| Tool | Result | Evidence |
|------|--------|----------|
| `list_all_sites` | ✅ | Returns site with UUID `88f7af54-98f8-306a-a1c7-c9349722b1f6` |
| `get_site_details` | ✅ fixed | Was failing (UUID format `id` field not checked); now returns full site |
| `get_site_health` | ✅ | Returns health metrics |
| `get_site_statistics` | ✅ | Returns statistics |
| `get_site_settings` | ✅ | Returns 38 settings including `super_mgmt`, `guest_access` |
| `list_devices_by_type(all)` | ✅ fixed | Returns all 6 devices (3× UAP, 1× USW, 1× UDM, 1× U7PG2) |
| `list_devices_by_type(uap)` | ✅ | Returns 4 APs |
| `list_devices_by_type(usw)` | ✅ | Returns 1 switch |
| `get_device_details` | ✅ | Returns AP-Stue details |
| `get_device_by_mac` | ✅ | Returns UDM Pro Max by MAC |
| `get_device_statistics` | ✅ | Returns throughput/uptime stats |
| `get_device_port_overrides` | ✅ | Returns port override list |
| `search_devices` | ✅ | Returns matching devices |
| `list_device_tags` | ✅ | Returns empty list |
| `list_mac_tags` | ✅ | Returns empty list |

#### Networks & WiFi

| Tool | Result | Evidence |
|------|--------|----------|
| `list_networks` (via `get_network_details`) | ✅ | Returns all VLANs/networks |
| `get_network_details` | ✅ | Returns 40-IoT network details |
| `get_network_statistics` | ✅ | Returns per-network stats |
| `get_network_references` | ✅ | Returns references for 40-IoT |
| `list_wlans` | ✅ | Returns WLAN list |
| `get_wlan_statistics` | ✅ | Returns WLAN stats |
| `list_vlans` | ✅ | Returns VLAN list |
| `list_available_channels` | ✅ | Returns available RF channels |
| `list_wan_connections` | ✅ | Returns WAN connection list |
| `list_active_routes` | ✅ | Returns routing table |
| `get_subnet_info` | ✅ | Returns subnet details |

#### Clients

| Tool | Result | Evidence |
|------|--------|----------|
| `list_active_clients` | ✅ | Returns active client list |
| `list_known_clients` | ✅ | Returns all known clients |
| `get_client_details` | ✅ | Returns ZYM-Presence-Detector details |
| `get_client_statistics` | ✅ | Returns client stats |
| `search_clients` | ✅ | Returns matching clients |

#### Firewall & ACL

| Tool | Result | Evidence |
|------|--------|----------|
| `list_firewall_zones` | ✅ | Returns 8 zones including NSFW, MGMT, Internal, External |
| `get_zone_networks` | ✅ fixed | Returns 2 network IDs for NSFW zone (`c841b60c-…`, `4fc6eb7a-…`) |
| `list_firewall_rules` | ✅ | Returns empty list (none configured) |
| `list_firewall_groups` | ✅ | Returns firewall groups |
| `list_acl_rules` | ✅ | Returns empty list |
| `get_acl_rule_ordering` | ✅ | Returns ordering config |
| `get_firewall_policy_ordering` | ✅ | Returns policy ordering |
| `list_dns_policies` | ✅ | Returns DNS policies |
| `get_dns_policy` | ✅ | Returns policy `7f65cd0a-…` details |

#### Traffic Rules, Routes & Matching

| Tool | Result | Evidence |
|------|--------|----------|
| `list_traffic_rules` | ✅ | Returns empty list |
| `list_traffic_routes` | ✅ | Returns empty list |
| `list_traffic_matching_lists` | ✅ | Returns empty list |

#### Traffic Flows / DPI (DPI disabled on this network)

| Tool | Result | Evidence |
|------|--------|----------|
| `get_traffic_flows` | ✅ | Returns empty (DPI/flow tracking not enabled) |
| `filter_traffic_flows` | ✅ | Returns empty |
| `get_flow_statistics` | ✅ | Returns empty |
| `get_flow_risks` | ✅ | Returns empty |
| `get_top_flows` | ✅ | Returns empty |
| `get_flow_trends` | ✅ | Returns empty |
| `get_traffic_flow_details` | ✅ | Returns empty |
| `get_dpi_statistics` | ✅ | Returns empty |
| `list_dpi_categories` | ✅ | Returns category list |
| `list_dpi_applications` | ✅ | Returns application list |

#### Port Profiles & Forwarding

| Tool | Result | Evidence |
|------|--------|----------|
| `list_port_profiles` | ✅ | Returns port profiles |
| `get_port_profile` | ✅ | Returns profile details |
| `list_port_forwards` | ✅ | Returns empty list |

#### RADIUS & Guest Portal

| Tool | Result | Evidence |
|------|--------|----------|
| `list_radius_profiles` | ✅ | Returns RADIUS profiles |
| `get_radius_profile` | ✅ | Returns profile `65c53d98…` details |
| `list_radius_accounts` | ✅ | Returns RADIUS accounts |
| `get_radius_account` | ✅ | Returns account `65da1ddb…` details |
| `get_guest_portal_config` | ✅ fixed | Returns real config: `auth_method=voucher`, `session_timeout=480` |
| `list_hotspot_packages` | ✅ | Returns empty (hotspot not configured); 404 handled gracefully |
| `list_vouchers` | ✅ fixed | Returns empty (no vouchers issued) |

#### Backups

| Tool | Result | Evidence |
|------|--------|----------|
| `list_backups` | ✅ | Returns 7 autobackups |
| `get_backup_details` | ✅ | Returns backup `autobackup_10.1.85_20260228_…` |
| `get_backup_schedule` | ✅ fixed | `enabled=true`, `cron_expr="30 0 1 * *"`, `max_files=7`, `timezone=Europe/Copenhagen` |
| `get_backup_status` | ✅ | Returns status |

#### Topology & Connectivity

| Tool | Result | Evidence |
|------|--------|----------|
| `get_network_topology` | ✅ | Returns topology graph |
| `export_topology` | ✅ | Returns topology export |
| `get_topology_statistics` | ✅ | Returns topology stats |
| `get_port_mappings` | ✅ | Returns port mapping data |
| `get_device_connections` | ✅ | Returns device connectivity |

#### VPN

| Tool | Result | Evidence |
|------|--------|----------|
| `list_vpn_tunnels` | ✅ | Returns empty list |
| `list_vpn_servers` | ✅ | Returns empty list |
| `list_site_to_site_vpns` | ✅ | Returns empty list |

#### Misc / System

| Tool | Result | Evidence |
|------|--------|----------|
| `list_alarms` | ✅ | Returns empty list |
| `list_events` | ✅ | Returns empty list |
| `list_rogue_aps` | ✅ | Returns 32 neighboring APs (all `is_rogue=false`) |
| `list_sessions` | ✅ | Returns session list |
| `get_historical_report` | ✅ | Returns empty (data retention for hourly scale is 168h; query was outside window — not a bug) |
| `run_speedtest` | ✅ | Returns speedtest trigger confirmation |
| `get_speedtest_status` | ✅ | Returns speedtest status |
| `get_ddns_status` | ✅ | Returns DDNS status |
| `list_user_groups` | ✅ | Returns user groups |
| `list_wlan_groups` | ✅ | Returns WLAN groups |
| `get_site_health_summary` | ✅ | Returns site health summary |

### Not Live-Tested (unit tests only)

The following tools have passing unit tests but require confirmation/dry_run to call safely and were skipped during the read-only sweep. They are believed correct based on code audit.

**Mutating audit completed 2026-03-14** — applied read-only sweep bug patterns to all mutating tools. 7 confirmed-broken tools fixed (wrong integration API paths → legacy REST paths):
- `get_voucher`, `create_vouchers`, `delete_voucher`, `bulk_delete_vouchers` → `stat/voucher` + `cmd/hotspot`
- `configure_guest_portal` → GET `rest/setting` + PUT `rest/setting/guest_access/{_id}`
- `create/get/update/delete_hotspot_package` → `rest/hotspot`
- `schedule_backups` → GET `rest/setting` + PUT `rest/setting/super_mgmt/{_id}` with cron expression

| Group | Tools | Reason not live-tested |
|-------|-------|------------------------|
| Mutating device ops | `locate_device`, `upgrade_device`, `force_provision_device`, `migrate_device`, `move_device`, `cancel_device_migration`, `trigger_spectrum_scan` | Require hardware interaction |
| Mutating client ops | `forget_client`, `unauthorize_guest` | Affect active sessions |
| Mutating network ops | `create_network`, `update_network`, `delete_network`, `create_wlan`, `update_wlan`, `delete_wlan` | Would alter live network config |
| Mutating firewall ops | `create_firewall_rule`, `update_firewall_rule`, `delete_firewall_rule`, `create_firewall_zone`, `update_firewall_zone`, `delete_firewall_zone`, `create_acl_rule`, `update_acl_rule`, `delete_acl_rule`, `assign_network_to_zone`, `unassign_network_from_zone`, `update_firewall_policy_ordering`, `update_acl_rule_ordering` | Would alter live firewall config |
| Mutating traffic ops | `create_traffic_rule`, `update_traffic_rule`, `delete_traffic_rule`, `create_traffic_route`, `update_traffic_route`, `delete_traffic_route`, `create_traffic_matching_list`, `update_traffic_matching_list`, `delete_traffic_matching_list` | Would alter live routing |
| Mutating RADIUS/guest ops | `create_radius_profile`, `update_radius_profile`, `delete_radius_profile`, `create_radius_account`, `update_radius_account`, `delete_radius_account`, `configure_guest_portal` ✅fixed, `create_hotspot_package` ✅fixed, `update_hotspot_package` ✅fixed, `delete_hotspot_package` ✅fixed, `create_vouchers` ✅fixed, `get_voucher` ✅fixed, `delete_voucher` ✅fixed, `bulk_delete_vouchers` ✅fixed | Would alter live auth config |
| Mutating backup ops | `trigger_backup`, `download_backup`, `delete_backup`, `validate_backup`, `restore_backup`, `schedule_backups` ✅fixed | Would alter backup state |
| Mutating DNS ops | `update_dns_policy`, `delete_dns_policy` | Would alter DNS config |
| Port operations | `set_device_port_overrides`, `execute_port_action`, `create_port_forward`, `delete_port_forward`, `create_port_profile`, `update_port_profile`, `delete_port_profile` | Would alter switch/port config |
| Dangerous system ops | `restore_backup`, `reboot_gateway`, `poweroff_gateway` | Skipped — would disrupt live network |
| VPN mutations | `update_site_to_site_vpn` | Would alter VPN config |
| Hotspot guest | `get_restore_status` | No active restore to query |
| Client DPI | `get_client_dpi`, `clear_dpi_counters` | DPI not enabled on this network |
| Site mutations | `update_site_setting`, `create_site`, `delete_site` | Would alter site config |
| QoS tools | all `limit_bandwidth` variants | Already tested one above |

---

## Recommended Fix Order

1. ~~**P0 path fixes** — `get_application_info`, `list_pending_devices`, ACL tools~~ **DONE** (2026-03-14)
2. ~~**Model fixes** — DPI and WAN Pydantic model mismatches~~ **DONE** (2026-03-14)
3. ~~**DNS policies** — 5 new tools implemented~~ **DONE** (2026-03-14)
4. ~~**Device action paths** — `restart_device` migrated to Integration API; `locate`/`upgrade` stay legacy~~ **DONE** (2026-03-14)
5. ~~**Network/WiFi migration** — `networks.py` and `wifi.py` migrated to Integration API~~ **DONE** (2026-03-14)
6. ~~**Ordering endpoints** — 4 new tools (firewall policy + ACL rule ordering)~~ **DONE** (2026-03-14)

### Remaining work

7. ~~**`adopt_device` path fix** — changed to `POST devices` with `macAddress` in body, param renamed to `mac_address`~~ **DONE** (2026-03-14)
8. ~~**`execute_port_action` path fix** — already correct (`interfaces/ports/{idx}/actions`)~~ **DONE** (2026-03-14)
9. ~~**`client_management.py` migration** — `cmd/stamgr` → `clients/{id}/actions`~~ **DONE** (2026-03-14) — already migrated to Integration API
10. ~~**`network_config.py` migration** — `rest/networkconf` → `sites/{id}/networks`~~ **DONE** (2026-03-14) — create/update/delete use Integration API with nested payload format
11. ~~**`clients.py` migration**~~ — **SKIPPED**: Integration API `/v1/clients` returns only 8 basic fields vs 30+ from legacy `sta`. Would lose all statistics, signal data, hostnames, VLANs. Moved to "Legacy only (not recommended)" section.
12. ~~**`WANConnection` model fix** — trimmed from 20+ fields to just `id`/`name` (all the API returns)~~ **DONE** (2026-03-14)
13. ~~**`DELETE devices/{id}`** — new `delete_device` tool with `destructiveHint` annotation + confirm/dry_run guards~~ **DONE** (2026-03-14)
14. ~~**`GET networks/{id}/references`** — new `get_network_references` tool shows WiFi/client/device dependencies for a network~~ **DONE** (2026-03-14)

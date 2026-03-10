from __future__ import annotations

from fastapi import HTTPException

from ..core.ovn_nb import get_ovn_nb_client
from ..models.topology import (
    LogicalRouterDetail,
    LogicalRouterPort,
    LogicalRouterSummary,
    LogicalSwitchDetail,
    LogicalSwitchPort,
    LogicalSwitchSummary,
)


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, list):
        if not value:
            return None
        return bool(value[0])
    if isinstance(value, bool):
        return value
    return None


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _row_name(value: object) -> str | None:
    if value is None:
        return None
    return getattr(value, "name", None) or str(getattr(value, "uuid", value))


class TopologyService:
    def __init__(self) -> None:
        self.nb_client = get_ovn_nb_client()

    def list_switches(self) -> list[LogicalSwitchSummary]:
        idl = self.nb_client.get_idl()
        switches = [
            LogicalSwitchSummary(
                uuid=str(row.uuid),
                name=getattr(row, "name", ""),
                port_count=len(getattr(row, "ports", [])),
                acl_count=len(getattr(row, "acls", [])),
                load_balancer_count=len(getattr(row, "load_balancer", [])),
                external_ids=dict(getattr(row, "external_ids", {})),
            )
            for row in idl.tables["Logical_Switch"].rows.values()
        ]
        return sorted(switches, key=lambda item: item.name)

    def get_switch(self, switch_ref: str) -> LogicalSwitchDetail:
        row = self._find_row("Logical_Switch", switch_ref)
        ports = [
            LogicalSwitchPort(
                uuid=str(port.uuid),
                name=getattr(port, "name", ""),
                type=getattr(port, "type", ""),
                addresses=_string_list(getattr(port, "addresses", [])),
                port_security=_string_list(getattr(port, "port_security", [])),
                enabled=_bool_or_none(getattr(port, "enabled", None)),
                external_ids=dict(getattr(port, "external_ids", {})),
            )
            for port in getattr(row, "ports", [])
        ]
        return LogicalSwitchDetail(
            uuid=str(row.uuid),
            name=getattr(row, "name", ""),
            port_count=len(getattr(row, "ports", [])),
            acl_count=len(getattr(row, "acls", [])),
            load_balancer_count=len(getattr(row, "load_balancer", [])),
            external_ids=dict(getattr(row, "external_ids", {})),
            ports=sorted(ports, key=lambda item: item.name),
        )

    def list_routers(self) -> list[LogicalRouterSummary]:
        idl = self.nb_client.get_idl()
        routers = [
            LogicalRouterSummary(
                uuid=str(row.uuid),
                name=getattr(row, "name", ""),
                port_count=len(getattr(row, "ports", [])),
                static_route_count=len(getattr(row, "static_routes", [])),
                nat_count=len(getattr(row, "nat", [])),
                external_ids=dict(getattr(row, "external_ids", {})),
            )
            for row in idl.tables["Logical_Router"].rows.values()
        ]
        return sorted(routers, key=lambda item: item.name)

    def get_router(self, router_ref: str) -> LogicalRouterDetail:
        row = self._find_row("Logical_Router", router_ref)
        ports = [
            LogicalRouterPort(
                uuid=str(port.uuid),
                name=getattr(port, "name", ""),
                mac=getattr(port, "mac", ""),
                networks=_string_list(getattr(port, "networks", [])),
                enabled=_bool_or_none(getattr(port, "enabled", None)),
                peer=_row_name(getattr(port, "peer", None)),
                external_ids=dict(getattr(port, "external_ids", {})),
            )
            for port in getattr(row, "ports", [])
        ]
        return LogicalRouterDetail(
            uuid=str(row.uuid),
            name=getattr(row, "name", ""),
            port_count=len(getattr(row, "ports", [])),
            static_route_count=len(getattr(row, "static_routes", [])),
            nat_count=len(getattr(row, "nat", [])),
            external_ids=dict(getattr(row, "external_ids", {})),
            ports=sorted(ports, key=lambda item: item.name),
        )

    def _find_row(self, table_name: str, reference: str):
        idl = self.nb_client.get_idl()
        rows = idl.tables[table_name].rows.values()
        for row in rows:
            if str(row.uuid) == reference or getattr(row, "name", None) == reference:
                return row
        raise HTTPException(status_code=404, detail=f"{table_name} {reference!r} not found.")

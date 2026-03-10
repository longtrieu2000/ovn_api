from __future__ import annotations

from pydantic import BaseModel, Field


class LogicalSwitchPort(BaseModel):
    uuid: str
    name: str
    type: str = ""
    addresses: list[str] = Field(default_factory=list)
    port_security: list[str] = Field(default_factory=list)
    enabled: bool | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)


class LogicalSwitchSummary(BaseModel):
    uuid: str
    name: str
    port_count: int
    acl_count: int
    load_balancer_count: int
    external_ids: dict[str, str] = Field(default_factory=dict)


class LogicalSwitchDetail(LogicalSwitchSummary):
    ports: list[LogicalSwitchPort] = Field(default_factory=list)


class LogicalRouterPort(BaseModel):
    uuid: str
    name: str
    mac: str = ""
    networks: list[str] = Field(default_factory=list)
    enabled: bool | None = None
    peer: str | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)


class LogicalRouterSummary(BaseModel):
    uuid: str
    name: str
    port_count: int
    static_route_count: int
    nat_count: int
    external_ids: dict[str, str] = Field(default_factory=dict)


class LogicalRouterDetail(LogicalRouterSummary):
    ports: list[LogicalRouterPort] = Field(default_factory=list)

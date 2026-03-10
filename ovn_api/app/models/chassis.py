from __future__ import annotations

from pydantic import BaseModel, Field


class ChassisSummary(BaseModel):
    uuid: str
    name: str
    hostname: str
    nb_cfg: int | None = None
    transport_types: list[str] = Field(default_factory=list)
    encap_ips: list[str] = Field(default_factory=list)
    port_binding_count: int
    other_config: dict[str, str] = Field(default_factory=dict)
    external_ids: dict[str, str] = Field(default_factory=dict)


class ChassisBinding(BaseModel):
    logical_port: str
    type: str
    datapath_uuid: str | None = None
    tunnel_key: int | None = None
    up: bool | None = None
    parent_port: str | None = None
    chassis: str | None = None
    additional_chassis: list[str] = Field(default_factory=list)
    options: dict[str, str] = Field(default_factory=dict)
    external_ids: dict[str, str] = Field(default_factory=dict)


class ChassisBindingsResponse(BaseModel):
    chassis: str
    binding_count: int
    bindings: list[ChassisBinding] = Field(default_factory=list)

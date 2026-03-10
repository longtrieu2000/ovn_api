from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LogicalFlow(BaseModel):
    uuid: str
    logical_datapath: str | None = None
    table_id: int | None = None
    priority: int | None = None
    match: str = ""
    actions: str = ""
    external_ids: dict[str, str] = Field(default_factory=dict)


class OpenFlowDump(BaseModel):
    bridge: str
    flow_count: int
    lines: list[str] = Field(default_factory=list)
    raw: str

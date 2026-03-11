from __future__ import annotations

from collections import Counter

from ..core.ovn_nb import get_ovn_nb_client
from ..core.ovn_sb import get_ovn_sb_client
from ..core.ovs import get_ovs_command_client
from ..models.flow import LogicalFlow, LogicalFlowOrigin, LogicalFlowOriginSummary, OpenFlowDump


def _row_uuid(value: object) -> str | None:
    if value is None:
        return None
    uuid_value = getattr(value, "uuid", None)
    if uuid_value is not None:
        return str(uuid_value)
    return str(value)


def _normalize_uuid(value: object | None) -> str | None:
    if value is None:
        return None
    uuid_value = str(value).strip().lower()
    return uuid_value or None


class FlowService:
    def __init__(self) -> None:
        self.nb_client = get_ovn_nb_client()
        self.sb_client = get_ovn_sb_client()
        self.ovs_client = get_ovs_command_client()

    def _origin_indexes(self, nb_idl: object | None = None) -> tuple[set[str], set[str]]:
        if nb_idl is None:
            nb_idl = self.nb_client.get_idl()
        acl_ids = {_normalize_uuid(row.uuid) for row in nb_idl.tables["ACL"].rows.values()}
        nat_ids = {_normalize_uuid(row.uuid) for row in nb_idl.tables["NAT"].rows.values()}
        return {uuid for uuid in acl_ids if uuid}, {uuid for uuid in nat_ids if uuid}

    def _classify_origin(
        self,
        external_ids: dict[str, str],
        acl_ids: set[str],
        nat_ids: set[str],
    ) -> tuple[str | None, LogicalFlowOrigin, str | None]:
        stage_hint = _normalize_uuid(external_ids.get("stage-hint"))
        if stage_hint in acl_ids:
            return stage_hint, "acl", stage_hint
        if stage_hint in nat_ids:
            return stage_hint, "nat", stage_hint
        return stage_hint, "other", None

    def list_logical_flows(
        self,
        table_id: int | None = None,
        origin: LogicalFlowOrigin | None = None,
        origin_uuid: str | None = None,
    ) -> list[LogicalFlow]:
        sb_idl = self.sb_client.get_idl()
        acl_ids, nat_ids = self._origin_indexes()
        normalized_origin_uuid = _normalize_uuid(origin_uuid)
        flows: list[LogicalFlow] = []
        for row in sb_idl.tables["Logical_Flow"].rows.values():
            row_table_id = getattr(row, "table_id", None)
            if table_id is not None and row_table_id != table_id:
                continue
            external_ids = dict(getattr(row, "external_ids", {}))
            stage_hint, origin_type, resolved_origin_uuid = self._classify_origin(
                external_ids,
                acl_ids,
                nat_ids,
            )
            if origin is not None and origin_type != origin:
                continue
            if normalized_origin_uuid is not None and resolved_origin_uuid != normalized_origin_uuid:
                continue

            flows.append(
                LogicalFlow(
                    uuid=str(row.uuid),
                    logical_datapath=_row_uuid(getattr(row, "logical_datapath", None)),
                    table_id=row_table_id,
                    priority=getattr(row, "priority", None),
                    match=getattr(row, "match", ""),
                    actions=getattr(row, "actions", ""),
                    stage_name=external_ids.get("stage-name"),
                    stage_hint=stage_hint,
                    source=external_ids.get("source"),
                    origin_type=origin_type,
                    origin_uuid=resolved_origin_uuid,
                    external_ids=external_ids,
                )
            )

        return sorted(flows, key=lambda flow: (flow.table_id or -1, -(flow.priority or -1), flow.uuid))

    def get_logical_flow_origin_summary(self) -> LogicalFlowOriginSummary:
        nb_idl = self.nb_client.get_idl()
        sb_idl = self.sb_client.get_idl()
        acl_ids, nat_ids = self._origin_indexes(nb_idl)

        acl_flow_counts: Counter[str] = Counter()
        nat_flow_counts: Counter[str] = Counter()
        total_count = 0

        for row in sb_idl.tables["Logical_Flow"].rows.values():
            total_count += 1
            external_ids = dict(getattr(row, "external_ids", {}))
            _, origin_type, origin_uuid = self._classify_origin(external_ids, acl_ids, nat_ids)
            if origin_type == "acl" and origin_uuid is not None:
                acl_flow_counts[origin_uuid] += 1
            elif origin_type == "nat" and origin_uuid is not None:
                nat_flow_counts[origin_uuid] += 1

        acl_logical_flow_count = sum(acl_flow_counts.values())
        nat_logical_flow_count = sum(nat_flow_counts.values())
        return LogicalFlowOriginSummary(
            logical_flow_count=total_count,
            acl_logical_flow_count=acl_logical_flow_count,
            nat_logical_flow_count=nat_logical_flow_count,
            other_logical_flow_count=total_count - acl_logical_flow_count - nat_logical_flow_count,
            acl_count=len(nb_idl.tables["ACL"].rows),
            nat_count=len(nb_idl.tables["NAT"].rows),
            acl_with_logical_flows_count=len(acl_flow_counts),
            nat_with_logical_flows_count=len(nat_flow_counts),
        )

    def get_openflow_flows(self, bridge: str) -> OpenFlowDump:
        raw = self.ovs_client.dump_openflow_flows(bridge=bridge)
        lines = [line for line in raw.splitlines() if line.strip()]
        flow_lines = [line for line in lines if not line.startswith("NXST_FLOW reply")]
        return OpenFlowDump(
            bridge=bridge,
            flow_count=len(flow_lines),
            lines=flow_lines,
            raw=raw,
        )

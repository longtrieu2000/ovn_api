from __future__ import annotations

from collections import Counter

from ..core.ovn_nb import get_ovn_nb_client
from ..core.ovn_sb import get_ovn_sb_client
from ..core.ovs import get_ovs_command_client
from ..models.flow import (
    LogicalFlow,
    LogicalFlowOriginFilter,
    LogicalFlowOriginSummary,
    LogicalFlowOriginType,
    OpenFlowDump,
)


ACL_STAGE_NAMES = frozenset(
    {
        "ls_in_pre_acl",
        "ls_out_pre_acl",
        "ls_in_acl_hint",
        "ls_out_acl_hint",
        "ls_in_acl_eval",
        "ls_out_acl_eval",
        "ls_in_acl_sample",
        "ls_out_acl_sample",
        "ls_in_acl_action",
        "ls_out_acl_action",
        "ls_in_acl_after_lb_eval",
        "ls_in_acl_after_lb_sample",
        "ls_in_acl_after_lb_action",
    }
)

NAT_STAGE_NAMES = frozenset(
    {
        "ls_in_nat_hairpin",
        "lr_in_unsnat",
        "lr_in_post_unsnat",
        "lr_in_dnat",
        "lr_out_undnat",
        "lr_out_post_undnat",
        "lr_out_snat",
        "lr_out_post_snat",
    }
)


def _row_uuid(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set, frozenset)):
        if not value:
            return None
        first_item = next(iter(value))
        return _row_uuid(first_item)
    uuid_value = getattr(value, "uuid", None)
    if uuid_value is not None:
        return str(uuid_value)
    return str(value)


def _normalize_uuid(value: object | None) -> str | None:
    if value is None:
        return None
    uuid_value = str(value).strip().lower()
    return uuid_value or None


def _uuid_prefix(uuid_value: str) -> str:
    return uuid_value.split("-", 1)[0]


def _build_unique_prefix_index(uuid_values: set[str]) -> dict[str, str]:
    prefix_counts = Counter(_uuid_prefix(uuid_value) for uuid_value in uuid_values)
    return {
        _uuid_prefix(uuid_value): uuid_value
        for uuid_value in uuid_values
        if prefix_counts[_uuid_prefix(uuid_value)] == 1
    }


class FlowService:
    def __init__(self) -> None:
        self.nb_client = get_ovn_nb_client()
        self.sb_client = get_ovn_sb_client()
        self.ovs_client = get_ovs_command_client()

    def _origin_indexes(
        self,
        nb_idl: object | None = None,
    ) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
        if nb_idl is None:
            nb_idl = self.nb_client.get_idl()
        acl_ids = {
            uuid for uuid in (_normalize_uuid(row.uuid) for row in nb_idl.tables["ACL"].rows.values()) if uuid
        }
        nat_ids = {
            uuid for uuid in (_normalize_uuid(row.uuid) for row in nb_idl.tables["NAT"].rows.values()) if uuid
        }

        acl_prefixes = _build_unique_prefix_index(acl_ids)
        nat_prefixes = _build_unique_prefix_index(nat_ids)
        return (
            {uuid: uuid for uuid in acl_ids},
            acl_prefixes,
            {uuid: uuid for uuid in nat_ids},
            nat_prefixes,
        )

    def _resolve_origin_uuid(
        self,
        stage_hint: str | None,
        full_ids: dict[str, str],
        prefix_ids: dict[str, str],
    ) -> str | None:
        if stage_hint is None:
            return None
        if stage_hint in full_ids:
            return full_ids[stage_hint]
        if stage_hint in prefix_ids:
            return prefix_ids[stage_hint]
        return None

    def _is_acl_stage(self, stage_name: str | None) -> bool:
        return stage_name in ACL_STAGE_NAMES if stage_name is not None else False

    def _is_nat_stage(self, stage_name: str | None) -> bool:
        return stage_name in NAT_STAGE_NAMES if stage_name is not None else False

    def _matches_origin_filter(
        self,
        origin_type: LogicalFlowOriginType,
        origin_filter: LogicalFlowOriginFilter | None,
    ) -> bool:
        if origin_filter is None:
            return True
        if origin_filter == "acl":
            return origin_type in {"acl_exact", "acl_stage_generic"}
        if origin_filter == "nat":
            return origin_type in {"nat_exact", "nat_stage_generic"}
        return origin_type == origin_filter

    def _classify_origin(
        self,
        stage_name: str | None,
        external_ids: dict[str, str],
        acl_full_ids: dict[str, str],
        acl_prefix_ids: dict[str, str],
        nat_full_ids: dict[str, str],
        nat_prefix_ids: dict[str, str],
    ) -> tuple[str | None, LogicalFlowOriginType, str | None]:
        stage_hint = _normalize_uuid(external_ids.get("stage-hint"))
        acl_origin_uuid = self._resolve_origin_uuid(stage_hint, acl_full_ids, acl_prefix_ids)
        if acl_origin_uuid is not None:
            return stage_hint, "acl_exact", acl_origin_uuid

        nat_origin_uuid = self._resolve_origin_uuid(stage_hint, nat_full_ids, nat_prefix_ids)
        if nat_origin_uuid is not None:
            return stage_hint, "nat_exact", nat_origin_uuid

        if self._is_acl_stage(stage_name):
            return stage_hint, "acl_stage_generic", None
        if self._is_nat_stage(stage_name):
            return stage_hint, "nat_stage_generic", None
        return stage_hint, "other", None

    def list_logical_flows(
        self,
        table_id: int | None = None,
        origin: LogicalFlowOriginFilter | None = None,
        origin_uuid: str | None = None,
    ) -> list[LogicalFlow]:
        sb_idl = self.sb_client.get_idl()
        acl_full_ids, acl_prefix_ids, nat_full_ids, nat_prefix_ids = self._origin_indexes()
        normalized_origin_uuid = _normalize_uuid(origin_uuid)
        flows: list[LogicalFlow] = []
        for row in sb_idl.tables["Logical_Flow"].rows.values():
            row_table_id = getattr(row, "table_id", None)
            if table_id is not None and row_table_id != table_id:
                continue
            external_ids = dict(getattr(row, "external_ids", {}))
            stage_name = external_ids.get("stage-name")
            stage_hint, origin_type, resolved_origin_uuid = self._classify_origin(
                stage_name,
                external_ids,
                acl_full_ids,
                acl_prefix_ids,
                nat_full_ids,
                nat_prefix_ids,
            )
            if not self._matches_origin_filter(origin_type, origin):
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
                    stage_name=stage_name,
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
        acl_full_ids, acl_prefix_ids, nat_full_ids, nat_prefix_ids = self._origin_indexes(nb_idl)

        flow_counts: Counter[str] = Counter()
        acl_flow_counts: Counter[str] = Counter()
        nat_flow_counts: Counter[str] = Counter()
        total_count = 0

        for row in sb_idl.tables["Logical_Flow"].rows.values():
            total_count += 1
            external_ids = dict(getattr(row, "external_ids", {}))
            stage_name = external_ids.get("stage-name")
            _, origin_type, origin_uuid = self._classify_origin(
                stage_name,
                external_ids,
                acl_full_ids,
                acl_prefix_ids,
                nat_full_ids,
                nat_prefix_ids,
            )
            flow_counts[origin_type] += 1
            if origin_type == "acl_exact" and origin_uuid is not None:
                acl_flow_counts[origin_uuid] += 1
            elif origin_type == "nat_exact" and origin_uuid is not None:
                nat_flow_counts[origin_uuid] += 1

        acl_exact_logical_flow_count = flow_counts["acl_exact"]
        acl_stage_generic_logical_flow_count = flow_counts["acl_stage_generic"]
        nat_exact_logical_flow_count = flow_counts["nat_exact"]
        nat_stage_generic_logical_flow_count = flow_counts["nat_stage_generic"]
        acl_logical_flow_count = acl_exact_logical_flow_count + acl_stage_generic_logical_flow_count
        nat_logical_flow_count = nat_exact_logical_flow_count + nat_stage_generic_logical_flow_count
        return LogicalFlowOriginSummary(
            logical_flow_count=total_count,
            acl_logical_flow_count=acl_logical_flow_count,
            acl_exact_logical_flow_count=acl_exact_logical_flow_count,
            acl_stage_generic_logical_flow_count=acl_stage_generic_logical_flow_count,
            nat_logical_flow_count=nat_logical_flow_count,
            nat_exact_logical_flow_count=nat_exact_logical_flow_count,
            nat_stage_generic_logical_flow_count=nat_stage_generic_logical_flow_count,
            other_logical_flow_count=flow_counts["other"],
            acl_count=len(acl_full_ids),
            nat_count=len(nat_full_ids),
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

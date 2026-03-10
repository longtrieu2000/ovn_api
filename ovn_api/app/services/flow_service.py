from __future__ import annotations

from ..core.ovn_nb import get_ovn_nb_client
from ..core.ovs import get_ovs_command_client
from ..models.flow import LogicalFlow, OpenFlowDump


def _row_uuid(value: object) -> str | None:
    if value is None:
        return None
    uuid_value = getattr(value, "uuid", None)
    if uuid_value is not None:
        return str(uuid_value)
    return str(value)


class FlowService:
    def __init__(self) -> None:
        self.nb_client = get_ovn_nb_client()
        self.ovs_client = get_ovs_command_client()

    def list_logical_flows(self, table_id: int | None = None) -> list[LogicalFlow]:
        idl = self.nb_client.get_idl()
        flows: list[LogicalFlow] = []
        for row in idl.tables["Logical_Flow"].rows.values():
            row_table_id = getattr(row, "table_id", None)
            if table_id is not None and row_table_id != table_id:
                continue

            flows.append(
                LogicalFlow(
                    uuid=str(row.uuid),
                    logical_datapath=_row_uuid(getattr(row, "logical_datapath", None)),
                    table_id=row_table_id,
                    priority=getattr(row, "priority", None),
                    match=getattr(row, "match", ""),
                    actions=getattr(row, "actions", ""),
                    external_ids=dict(getattr(row, "external_ids", {})),
                )
            )

        return sorted(flows, key=lambda flow: (flow.table_id or -1, -(flow.priority or -1), flow.uuid))

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

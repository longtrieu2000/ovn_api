from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import HTTPException

from ..config import get_settings
from ..core.ovn_nb import get_ovn_nb_client
from ..core.ovn_nbctl import get_ovn_nb_command_client
from ..core.ovn_sb import get_ovn_sb_client
from ..core.ovs import get_ovs_command_client
from ..models.traces import (
    CanaryCapabilitiesResponse,
    CanaryCapability,
    CanaryProbeRequest,
    CanaryProbeResult,
    CanaryProbeStage,
    CanaryResourceType,
)


OPENFLOW_CAPABLE_RESOURCE_TYPES = frozenset({"acl", "nat"})
SB_READY_RESOURCE_TYPES = frozenset({"logical_switch", "logical_router"})
PIPELINE_STAGE_NAMES = ("nb_committed", "sb_realized", "openflow_realized", "cleanup")
CANARY_RESOURCE_TYPES: tuple[CanaryResourceType, ...] = (
    "acl",
    "logical_flow",
    "nat",
    "nat_rule",
    "logical_switch",
    "network",
    "logical_router",
    "logical_switch_port",
    "logical_port",
    "logical_router_port",
    "subnet",
)
NB_TABLE_BY_RESOLVED_TYPE = {
    "acl": "ACL",
    "nat": "NAT",
    "logical_switch": "Logical_Switch",
    "logical_router": "Logical_Router",
    "logical_switch_port": "Logical_Switch_Port",
    "logical_router_port": "Logical_Router_Port",
}
SB_SIGNAL_BY_RESOLVED_TYPE = {
    "acl": "Logical_Flow external_ids[stage-hint] / token match",
    "nat": "Logical_Flow external_ids[stage-hint] / token match",
    "logical_switch": "Datapath_Binding type=logical-switch",
    "logical_router": "Datapath_Binding type=logical-router",
    "logical_switch_port": "Port_Binding.logical_port",
    "logical_router_port": "Port_Binding.logical_port",
}
TARGET_KIND_BY_RESOLVED_TYPE = {
    "acl": "logical_switch",
    "nat": "logical_router",
    "logical_switch_port": "logical_switch",
    "logical_router_port": "logical_router",
}


@dataclass
class PreparedProbe:
    probe_id: str
    requested_resource_type: CanaryResourceType
    resolved_resource_type: str
    resource_name: str
    target_name: str | None
    bridge: str
    timeout_s: float
    poll_interval_s: float
    openflow_expected: bool
    note: str | None
    nb_table: str
    context: dict[str, str] = field(default_factory=dict)
    create_command: list[str] = field(default_factory=list)
    setup_commands: list[list[str]] = field(default_factory=list)
    cleanup_commands: list[list[str]] = field(default_factory=list)
    setup_wait: tuple[str, str] | None = None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="milliseconds")


def _elapsed_ms(start: float, end: float | None = None) -> float:
    end_value = time.perf_counter() if end is None else end
    return round((end_value - start) * 1000, 3)


def _single_optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set, frozenset)):
        if not value:
            return None
        value = next(iter(value))
    return str(value)


def _row_uuid(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set, frozenset)):
        if not value:
            return None
        value = next(iter(value))
    uuid_value = getattr(value, "uuid", None)
    if uuid_value is not None:
        return str(uuid_value)
    return str(value)


def _row_name(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set, frozenset)):
        if not value:
            return None
        value = next(iter(value))
    return getattr(value, "name", None) or _row_uuid(value)


def _normalize_uuid(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def _uuid_prefix(uuid_value: str) -> str:
    return uuid_value.split("-", 1)[0]


def _limited_evidence(lines: list[str], *, limit: int = 5) -> list[str]:
    return lines[:limit]


def _probe_octets(probe_id: str) -> tuple[int, int, int, int]:
    seed = uuid.UUID(probe_id).int
    return (
        ((seed >> 8) % 254) + 1,
        (seed % 254) + 1,
        ((seed >> 24) % 254) + 1,
        ((seed >> 16) % 254) + 1,
    )


def _probe_mac(probe_id: str) -> str:
    octets = _probe_octets(probe_id)
    return f"aa:55:{octets[0]:02x}:{octets[1]:02x}:{octets[2]:02x}:{octets[3]:02x}"


class CanaryTraceService:
    def __init__(self) -> None:
        self.nb_client = get_ovn_nb_client()
        self.sb_client = get_ovn_sb_client()
        self.ovs_client = get_ovs_command_client()
        self.nb_command_client = get_ovn_nb_command_client()

    def run_probe(self, request: CanaryProbeRequest) -> CanaryProbeResult:
        prepared = self.prepare_probe(request)
        return self.run_prepared_probe(prepared)

    def prepare_probe(self, request: CanaryProbeRequest) -> PreparedProbe:
        return self._build_probe(request)

    def run_prepared_probe(self, prepared: PreparedProbe) -> CanaryProbeResult:
        result: CanaryProbeResult | None = None
        try:
            try:
                self._run_setup(prepared)
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
                result = self._setup_failed_result(prepared, detail)
            else:
                result = self._execute_probe(prepared)
            return result
        finally:
            cleanup_stage = self._run_cleanup(prepared)
            if result is not None:
                result.cleanup = cleanup_stage
                result.finished_at = _isoformat(_now_utc())
                result.status = self._derive_status(result)

    def get_capabilities(self) -> CanaryCapabilitiesResponse:
        settings = get_settings()
        return CanaryCapabilitiesResponse(
            sync_endpoint="/api/v1/traces/canary",
            async_submit_endpoint="/api/v1/traces/canary/runs",
            async_run_endpoint_template="/api/v1/traces/canary/runs/{probe_id}",
            execution_model=(
                "Sync endpoint blocks until the canary finishes. Async endpoint queues jobs in a single "
                "background worker while request/result metadata is persisted in the SQL trace store."
            ),
            store_scope=(
                "Persistent SQL trace store configured by TRACE_STORE_URL "
                f"(current dialect: {settings.trace_store_url.split(':', 1)[0]}). "
                "Worker queue is still process-local."
            ),
            pipeline_stages=list(PIPELINE_STAGE_NAMES),
            resources=[self._build_capability(resource_type) for resource_type in CANARY_RESOURCE_TYPES],
        )

    def _build_probe(self, request: CanaryProbeRequest) -> PreparedProbe:
        resolved_type, alias_note = self._resolve_resource_type(request.resource_type)
        openflow_expected = self._resolve_openflow_expectation(
            resolved_type=resolved_type,
            target_name=request.target_name,
            expect_openflow=request.expect_openflow,
        )

        note_parts = [alias_note] if alias_note else []
        if request.target_name and openflow_expected:
            note_parts.append(
                f"OpenFlow detection assumes the target datapath is realized on local bridge {request.bridge!r}."
            )

        probe_uuid = str(uuid.uuid4())
        probe_suffix = probe_uuid.split("-", 1)[0]
        probe_id = probe_uuid
        a_octet, b_octet, c_octet, d_octet = _probe_octets(probe_id)
        acl_probe_ip = f"198.18.{a_octet}.{b_octet}"
        nat_external_ip = f"203.0.113.{c_octet}"
        nat_logical_ip = f"198.19.{a_octet}.{b_octet}"
        router_network = f"100.64.{c_octet}.1/24"
        resource_name_map = {
            "acl": f"canary-acl-{probe_suffix}",
            "nat": f"nat:{nat_external_ip}->{nat_logical_ip}",
            "logical_switch": f"canary-ls-{probe_suffix}",
            "logical_router": f"canary-lr-{probe_suffix}",
            "logical_switch_port": f"canary-lsp-{probe_suffix}",
            "logical_router_port": f"canary-lrp-{probe_suffix}",
        }

        prepared = PreparedProbe(
            probe_id=probe_id,
            requested_resource_type=request.resource_type,
            resolved_resource_type=resolved_type,
            resource_name=resource_name_map[resolved_type],
            target_name=request.target_name,
            bridge=request.bridge,
            timeout_s=request.timeout_s,
            poll_interval_s=request.poll_interval_ms / 1000,
            openflow_expected=openflow_expected,
            note=None,
            nb_table="",
        )

        if resolved_type == "acl":
            switch_ref, setup_note, setup_commands, cleanup_commands, setup_wait = self._resolve_switch_target(
                request.target_name,
                probe_suffix,
            )
            prepared.nb_table = "ACL"
            prepared.context = {
                "switch_ref": switch_ref,
                "acl_name": prepared.resource_name,
                "acl_match": f"ip4.src=={acl_probe_ip}",
                "acl_direction": "to-lport",
                "acl_priority": "2001",
                "probe_ip": acl_probe_ip,
            }
            prepared.create_command = [
                "--type=switch",
                f"--name={prepared.resource_name}",
                "acl-add",
                switch_ref,
                prepared.context["acl_direction"],
                prepared.context["acl_priority"],
                prepared.context["acl_match"],
                "drop",
            ]
            prepared.setup_commands = setup_commands
            prepared.cleanup_commands = [
                [
                    "--if-exists",
                    "--type=switch",
                    "acl-del",
                    switch_ref,
                    prepared.context["acl_direction"],
                    prepared.context["acl_priority"],
                    prepared.context["acl_match"],
                ],
                *cleanup_commands,
            ]
            prepared.setup_wait = setup_wait
            if setup_note:
                note_parts.append(setup_note)
        elif resolved_type == "nat":
            router_ref, setup_note, setup_commands, cleanup_commands, setup_wait = self._resolve_router_target(
                request.target_name,
                probe_suffix,
            )
            prepared.nb_table = "NAT"
            prepared.context = {
                "router_ref": router_ref,
                "nat_type": "snat",
                "external_ip": nat_external_ip,
                "logical_ip": nat_logical_ip,
            }
            prepared.create_command = [
                "lr-nat-add",
                router_ref,
                prepared.context["nat_type"],
                prepared.context["external_ip"],
                prepared.context["logical_ip"],
            ]
            prepared.setup_commands = setup_commands
            prepared.cleanup_commands = [
                [
                    "--if-exists",
                    "lr-nat-del",
                    router_ref,
                    prepared.context["nat_type"],
                    prepared.context["logical_ip"],
                ],
                *cleanup_commands,
            ]
            prepared.setup_wait = setup_wait
            if setup_note:
                note_parts.append(setup_note)
        elif resolved_type == "logical_switch":
            prepared.nb_table = "Logical_Switch"
            prepared.context = {"switch_name": prepared.resource_name}
            prepared.create_command = ["ls-add", prepared.resource_name]
            prepared.cleanup_commands = [["--if-exists", "ls-del", prepared.resource_name]]
            if request.resource_type == "network":
                note_parts.append("In OVN, Neutron network maps most directly to Logical_Switch.")
        elif resolved_type == "logical_router":
            prepared.nb_table = "Logical_Router"
            prepared.context = {"router_name": prepared.resource_name}
            prepared.create_command = ["lr-add", prepared.resource_name]
            prepared.cleanup_commands = [["--if-exists", "lr-del", prepared.resource_name]]
        elif resolved_type == "logical_switch_port":
            switch_ref, setup_note, setup_commands, cleanup_commands, setup_wait = self._resolve_switch_target(
                request.target_name,
                probe_suffix,
            )
            prepared.nb_table = "Logical_Switch_Port"
            prepared.context = {
                "switch_ref": switch_ref,
                "port_name": prepared.resource_name,
            }
            prepared.create_command = ["lsp-add", switch_ref, prepared.resource_name]
            prepared.setup_commands = setup_commands
            prepared.cleanup_commands = [["--if-exists", "lsp-del", prepared.resource_name], *cleanup_commands]
            prepared.setup_wait = setup_wait
            if setup_note:
                note_parts.append(setup_note)
        elif resolved_type == "logical_router_port":
            router_ref, setup_note, setup_commands, cleanup_commands, setup_wait = self._resolve_router_target(
                request.target_name,
                probe_suffix,
            )
            prepared.nb_table = "Logical_Router_Port"
            prepared.context = {
                "router_ref": router_ref,
                "port_name": prepared.resource_name,
                "port_mac": _probe_mac(probe_id),
                "port_network": router_network,
            }
            prepared.create_command = [
                "lrp-add",
                router_ref,
                prepared.resource_name,
                prepared.context["port_mac"],
                prepared.context["port_network"],
            ]
            prepared.setup_commands = setup_commands
            prepared.cleanup_commands = [["--if-exists", "lrp-del", prepared.resource_name], *cleanup_commands]
            prepared.setup_wait = setup_wait
            if request.resource_type == "subnet":
                note_parts.append(
                    "OVN has no first-class Subnet table, so the probe uses a Logical_Router_Port with CIDR as a subnet proxy."
                )
            if setup_note:
                note_parts.append(setup_note)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported resource type: {resolved_type!r}")

        if resolved_type not in OPENFLOW_CAPABLE_RESOURCE_TYPES:
            if request.expect_openflow:
                note_parts.append(
                    f"OpenFlow stage is skipped for {resolved_type!r} because it does not have a stable 1:1 canary mapping on br-int."
                )
            prepared.openflow_expected = False
        elif request.target_name is None and prepared.openflow_expected:
            note_parts.append(
                "No target datapath was supplied, so OpenFlow detection may stay empty unless the temporary canary is realized on the local bridge."
            )

        prepared.note = " ".join(note_parts) or None
        return prepared

    def _build_capability(self, resource_type: CanaryResourceType) -> CanaryCapability:
        resolved_type, alias_note = self._resolve_resource_type(resource_type)
        openflow_supported = resolved_type in OPENFLOW_CAPABLE_RESOURCE_TYPES
        available_stages = [
            stage_name
            for stage_name in PIPELINE_STAGE_NAMES
            if openflow_supported or stage_name != "openflow_realized"
        ]

        notes: list[str] = []
        if alias_note:
            notes.append(alias_note)

        if resource_type == "network":
            notes.append("Neutron network maps to OVN Logical_Switch for this canary.")
        if resource_type == "subnet":
            notes.append("Subnet uses Logical_Router_Port as a CIDR-bearing proxy because OVN has no Subnet table.")
        if openflow_supported:
            notes.append("OpenFlow evidence is meaningful only when the target datapath is realized on the local bridge.")
            notes.append("Set target_name to an existing switch/router if you want OpenFlow enabled by default.")
        else:
            notes.append("OpenFlow stage is skipped because this resource has no stable 1:1 mapping to br-int flows.")

        return CanaryCapability(
            requested_resource_type=resource_type,
            resolved_resource_type=resolved_type,
            alias_for=resolved_type if resource_type != resolved_type else None,
            target_name_kind=TARGET_KIND_BY_RESOLVED_TYPE.get(resolved_type),
            nb_table=NB_TABLE_BY_RESOLVED_TYPE[resolved_type],
            sb_signal=SB_SIGNAL_BY_RESOLVED_TYPE[resolved_type],
            openflow_supported=openflow_supported,
            requires_target_name_for_openflow=openflow_supported,
            available_stages=available_stages,
            notes=notes,
        )

    def _execute_probe(self, prepared: PreparedProbe) -> CanaryProbeResult:
        started_at = _now_utc()
        start_perf = time.perf_counter()
        openflow_stage = (
            CanaryProbeStage(status="timeout", detail="Timed out waiting for matching OpenFlow.")
            if prepared.openflow_expected
            else CanaryProbeStage(status="skipped", detail="OpenFlow stage is disabled for this probe.")
        )
        nb_stage = CanaryProbeStage(status="timeout", detail="Timed out waiting for the resource to appear in OVN NB.")
        sb_stage = CanaryProbeStage(status="timeout", detail="Timed out waiting for the resource to appear in OVN SB.")

        try:
            self.nb_command_client.run(prepared.create_command)
        except HTTPException as exc:
            return CanaryProbeResult(
                probe_id=prepared.probe_id,
                requested_resource_type=prepared.requested_resource_type,
                resolved_resource_type=prepared.resolved_resource_type,
                resource_name=prepared.resource_name,
                target_name=prepared.target_name,
                started_at=_isoformat(started_at) or "",
                status="failed",
                openflow_expected=prepared.openflow_expected,
                note=prepared.note,
                nb_uuid=None,
                command_latency_ms=_elapsed_ms(start_perf),
                nb_committed=CanaryProbeStage(status="failed", detail=str(exc.detail)),
                sb_realized=CanaryProbeStage(status="failed", detail="NB creation failed; SB stage not evaluated."),
                openflow_realized=(
                    CanaryProbeStage(status="failed", detail="NB creation failed; OpenFlow stage not evaluated.")
                    if prepared.openflow_expected
                    else openflow_stage
                ),
                cleanup=CanaryProbeStage(status="skipped", detail="Cleanup pending."),
            )

        command_latency_ms = _elapsed_ms(start_perf)
        nb_seen_at: float | None = None
        sb_seen_at: float | None = None
        of_seen_at: float | None = None
        nb_uuid: str | None = None
        deadline = start_perf + prepared.timeout_s

        try:
            while time.perf_counter() <= deadline:
                if nb_uuid is None:
                    nb_row = self._find_nb_row(prepared)
                    if nb_row is not None:
                        nb_uuid = str(nb_row.uuid)
                        nb_seen_at = time.perf_counter()
                        nb_stage = CanaryProbeStage(
                            status="observed",
                            observed_at=_isoformat(_now_utc()),
                            latency_ms=_elapsed_ms(start_perf, nb_seen_at),
                            detail=f"{prepared.nb_table} row observed in OVN NB.",
                            evidence=[f"{prepared.nb_table}:{nb_uuid}"],
                        )

                if nb_uuid is not None and sb_seen_at is None:
                    sb_evidence = self._find_sb_evidence(prepared, nb_uuid)
                    if sb_evidence:
                        sb_seen_at = time.perf_counter()
                        sb_stage = CanaryProbeStage(
                            status="observed",
                            observed_at=_isoformat(_now_utc()),
                            latency_ms=_elapsed_ms(start_perf, sb_seen_at),
                            detail="Matching southbound state observed.",
                            evidence=_limited_evidence(sb_evidence),
                        )

                if prepared.openflow_expected and sb_seen_at is not None and of_seen_at is None:
                    openflow_evidence = self._find_openflow_evidence(prepared)
                    if openflow_evidence:
                        of_seen_at = time.perf_counter()
                        openflow_stage = CanaryProbeStage(
                            status="observed",
                            observed_at=_isoformat(_now_utc()),
                            latency_ms=_elapsed_ms(start_perf, of_seen_at),
                            detail=f"Matching OpenFlow observed on bridge {prepared.bridge!r}.",
                            evidence=_limited_evidence(openflow_evidence),
                        )

                if nb_uuid is not None and sb_seen_at is not None and (
                    not prepared.openflow_expected or of_seen_at is not None
                ):
                    break

                time.sleep(prepared.poll_interval_s)
        except HTTPException as exc:
            if nb_uuid is None:
                nb_stage = CanaryProbeStage(status="failed", detail=str(exc.detail))
                sb_stage = CanaryProbeStage(status="failed", detail="Probe stopped before SB polling.")
                if prepared.openflow_expected:
                    openflow_stage = CanaryProbeStage(status="failed", detail="Probe stopped before OpenFlow polling.")
            elif sb_seen_at is None:
                sb_stage = CanaryProbeStage(status="failed", detail=str(exc.detail))
                if prepared.openflow_expected:
                    openflow_stage = CanaryProbeStage(status="failed", detail="SB polling failed before OpenFlow.")
            elif prepared.openflow_expected and of_seen_at is None:
                openflow_stage = CanaryProbeStage(status="failed", detail=str(exc.detail))
            return CanaryProbeResult(
                probe_id=prepared.probe_id,
                requested_resource_type=prepared.requested_resource_type,
                resolved_resource_type=prepared.resolved_resource_type,
                resource_name=prepared.resource_name,
                target_name=prepared.target_name,
                started_at=_isoformat(started_at) or "",
                status="failed",
                openflow_expected=prepared.openflow_expected,
                note=prepared.note,
                nb_uuid=nb_uuid,
                command_latency_ms=command_latency_ms,
                nb_committed=nb_stage,
                sb_realized=sb_stage,
                openflow_realized=openflow_stage,
                cleanup=CanaryProbeStage(status="skipped", detail="Cleanup pending."),
                nb_to_sb_latency_ms=self._delta_ms(nb_seen_at, sb_seen_at),
                sb_to_openflow_latency_ms=self._delta_ms(sb_seen_at, of_seen_at),
                total_latency_ms=self._total_latency_ms(prepared.openflow_expected, sb_seen_at, of_seen_at, start_perf),
            )

        return CanaryProbeResult(
            probe_id=prepared.probe_id,
            requested_resource_type=prepared.requested_resource_type,
            resolved_resource_type=prepared.resolved_resource_type,
            resource_name=prepared.resource_name,
            target_name=prepared.target_name,
            started_at=_isoformat(started_at) or "",
            status="success",
            openflow_expected=prepared.openflow_expected,
            note=prepared.note,
            nb_uuid=nb_uuid,
            command_latency_ms=command_latency_ms,
            nb_committed=nb_stage,
            sb_realized=sb_stage,
            openflow_realized=openflow_stage,
            cleanup=CanaryProbeStage(status="skipped", detail="Cleanup pending."),
            nb_to_sb_latency_ms=self._delta_ms(nb_seen_at, sb_seen_at),
            sb_to_openflow_latency_ms=self._delta_ms(sb_seen_at, of_seen_at),
            total_latency_ms=self._total_latency_ms(prepared.openflow_expected, sb_seen_at, of_seen_at, start_perf),
        )

    def _setup_failed_result(self, prepared: PreparedProbe, detail: str) -> CanaryProbeResult:
        return CanaryProbeResult(
            probe_id=prepared.probe_id,
            requested_resource_type=prepared.requested_resource_type,
            resolved_resource_type=prepared.resolved_resource_type,
            resource_name=prepared.resource_name,
            target_name=prepared.target_name,
            started_at=_isoformat(_now_utc()) or "",
            status="failed",
            openflow_expected=prepared.openflow_expected,
            note=prepared.note,
            nb_uuid=None,
            command_latency_ms=0.0,
            nb_committed=CanaryProbeStage(status="failed", detail=f"Probe setup failed: {detail}"),
            sb_realized=CanaryProbeStage(status="failed", detail="Probe setup failed before SB observation."),
            openflow_realized=(
                CanaryProbeStage(status="failed", detail="Probe setup failed before OpenFlow observation.")
                if prepared.openflow_expected
                else CanaryProbeStage(status="skipped", detail="OpenFlow stage is disabled for this probe.")
            ),
            cleanup=CanaryProbeStage(status="skipped", detail="Cleanup pending."),
        )

    def _run_setup(self, prepared: PreparedProbe) -> None:
        for command in prepared.setup_commands:
            self.nb_command_client.run(command)
        if prepared.setup_wait is None:
            return
        wait_type, wait_name = prepared.setup_wait
        deadline = time.perf_counter() + prepared.timeout_s
        while time.perf_counter() <= deadline:
            nb_row = self._find_named_nb_row(wait_type, wait_name)
            if nb_row is not None:
                nb_uuid = str(nb_row.uuid)
                if wait_type in SB_READY_RESOURCE_TYPES and self._find_sb_parent_evidence(wait_type, nb_uuid):
                    return
            time.sleep(prepared.poll_interval_s)
        raise HTTPException(
            status_code=500,
            detail=f"Temporary {wait_type!r} {wait_name!r} did not become ready before the probe started.",
        )

    def _run_cleanup(self, prepared: PreparedProbe) -> CanaryProbeStage:
        if not prepared.cleanup_commands:
            return CanaryProbeStage(status="skipped", detail="No cleanup required.")
        cleanup_errors: list[str] = []
        for command in prepared.cleanup_commands:
            try:
                self.nb_command_client.run(command)
            except HTTPException as exc:
                cleanup_errors.append(f"{' '.join(command)} -> {exc.detail}")
        if cleanup_errors:
            return CanaryProbeStage(
                status="failed",
                detail="One or more cleanup commands failed.",
                evidence=_limited_evidence(cleanup_errors),
            )
        return CanaryProbeStage(
            status="observed",
            observed_at=_isoformat(_now_utc()),
            detail="Cleanup completed.",
        )

    def _resolve_resource_type(self, resource_type: CanaryResourceType) -> tuple[str, str | None]:
        aliases = {
            "logical_flow": (
                "acl",
                "Logical_Flow is generated in OVN SB, so this probe uses a canary ACL to force logical-flow creation.",
            ),
            "nat_rule": ("nat", None),
            "network": ("logical_switch", None),
            "logical_port": ("logical_switch_port", None),
            "subnet": ("logical_router_port", None),
        }
        if resource_type in aliases:
            return aliases[resource_type]
        return resource_type, None

    def _resolve_openflow_expectation(
        self,
        *,
        resolved_type: str,
        target_name: str | None,
        expect_openflow: bool | None,
    ) -> bool:
        if resolved_type not in OPENFLOW_CAPABLE_RESOURCE_TYPES:
            return False
        if expect_openflow is not None:
            return expect_openflow
        return target_name is not None

    def _resolve_switch_target(
        self,
        target_name: str | None,
        probe_suffix: str,
    ) -> tuple[str, str | None, list[list[str]], list[list[str]], tuple[str, str] | None]:
        if target_name is not None:
            row = self._require_nb_row("Logical_Switch", target_name)
            return str(row.uuid), None, [], [], None

        switch_name = f"canary-target-ls-{probe_suffix}"
        return (
            switch_name,
            f"A temporary logical switch {switch_name!r} is created as the canary target.",
            [["ls-add", switch_name]],
            [["--if-exists", "ls-del", switch_name]],
            ("logical_switch", switch_name),
        )

    def _resolve_router_target(
        self,
        target_name: str | None,
        probe_suffix: str,
    ) -> tuple[str, str | None, list[list[str]], list[list[str]], tuple[str, str] | None]:
        if target_name is not None:
            row = self._require_nb_row("Logical_Router", target_name)
            return str(row.uuid), None, [], [], None

        router_name = f"canary-target-lr-{probe_suffix}"
        return (
            router_name,
            f"A temporary logical router {router_name!r} is created as the canary target.",
            [["lr-add", router_name]],
            [["--if-exists", "lr-del", router_name]],
            ("logical_router", router_name),
        )

    def _require_nb_row(self, table_name: str, reference: str):
        row = self._find_named_or_uuid_row(table_name, reference)
        if row is None:
            raise HTTPException(status_code=404, detail=f"{table_name} {reference!r} not found.")
        return row

    def _find_named_nb_row(self, resource_type: str, name: str):
        table_name = "Logical_Switch" if resource_type == "logical_switch" else "Logical_Router"
        return self._find_named_or_uuid_row(table_name, name)

    def _find_named_or_uuid_row(self, table_name: str, reference: str):
        idl = self.nb_client.get_idl()
        for row in idl.tables[table_name].rows.values():
            if str(row.uuid) == reference or getattr(row, "name", None) == reference:
                return row
        return None

    def _find_nb_row(self, prepared: PreparedProbe):
        idl = self.nb_client.get_idl()
        rows = idl.tables[prepared.nb_table].rows.values()

        if prepared.resolved_resource_type == "acl":
            acl_name = prepared.context["acl_name"]
            acl_match = prepared.context["acl_match"]
            acl_direction = prepared.context["acl_direction"]
            acl_priority = int(prepared.context["acl_priority"])
            for row in rows:
                if getattr(row, "name", None) == acl_name:
                    return row
                if (
                    getattr(row, "match", None) == acl_match
                    and getattr(row, "direction", None) == acl_direction
                    and getattr(row, "priority", None) == acl_priority
                ):
                    return row
            return None

        if prepared.resolved_resource_type == "nat":
            nat_type = prepared.context["nat_type"]
            external_ip = prepared.context["external_ip"]
            logical_ip = prepared.context["logical_ip"]
            for row in rows:
                if (
                    getattr(row, "type", None) == nat_type
                    and getattr(row, "external_ip", None) == external_ip
                    and getattr(row, "logical_ip", None) == logical_ip
                ):
                    return row
            return None

        if prepared.resolved_resource_type == "logical_switch":
            switch_name = prepared.context["switch_name"]
            for row in rows:
                if getattr(row, "name", None) == switch_name:
                    return row
            return None

        if prepared.resolved_resource_type == "logical_router":
            router_name = prepared.context["router_name"]
            for row in rows:
                if getattr(row, "name", None) == router_name:
                    return row
            return None

        if prepared.resolved_resource_type == "logical_switch_port":
            port_name = prepared.context["port_name"]
            for row in rows:
                if getattr(row, "name", None) == port_name:
                    return row
            return None

        if prepared.resolved_resource_type == "logical_router_port":
            port_name = prepared.context["port_name"]
            for row in rows:
                if getattr(row, "name", None) == port_name:
                    return row
            return None

        return None

    def _find_sb_parent_evidence(self, resource_type: str, nb_uuid: str) -> list[str]:
        sb_idl = self.sb_client.get_idl()
        if resource_type == "logical_switch":
            return self._find_datapath_binding_evidence(sb_idl, nb_uuid, "logical-switch")
        if resource_type == "logical_router":
            return self._find_datapath_binding_evidence(sb_idl, nb_uuid, "logical-router")
        return []

    def _find_sb_evidence(self, prepared: PreparedProbe, nb_uuid: str) -> list[str]:
        sb_idl = self.sb_client.get_idl()
        if prepared.resolved_resource_type == "acl":
            return self._find_logical_flow_evidence(sb_idl, nb_uuid, prepared.context["probe_ip"])
        if prepared.resolved_resource_type == "nat":
            return self._find_logical_flow_evidence(
                sb_idl,
                nb_uuid,
                prepared.context["external_ip"],
                prepared.context["logical_ip"],
            )
        if prepared.resolved_resource_type == "logical_switch":
            return self._find_datapath_binding_evidence(sb_idl, nb_uuid, "logical-switch")
        if prepared.resolved_resource_type == "logical_router":
            return self._find_datapath_binding_evidence(sb_idl, nb_uuid, "logical-router")
        if prepared.resolved_resource_type in {"logical_switch_port", "logical_router_port"}:
            return self._find_port_binding_evidence(sb_idl, prepared.context["port_name"])
        return []

    def _find_datapath_binding_evidence(self, sb_idl, nb_uuid: str, expected_type: str) -> list[str]:
        evidence: list[str] = []
        for row in sb_idl.tables["Datapath_Binding"].rows.values():
            row_nb_uuid = _normalize_uuid(getattr(row, "nb_uuid", None))
            row_type = _single_optional_string(getattr(row, "type", None))
            external_ids = dict(getattr(row, "external_ids", {}))
            if row_type != expected_type:
                continue
            if row_nb_uuid != nb_uuid and _normalize_uuid(external_ids.get(expected_type)) != nb_uuid:
                continue
            evidence.append(
                "datapath="
                f"{row.uuid} type={row_type} tunnel_key={getattr(row, 'tunnel_key', None)} "
                f"name={external_ids.get('name')}"
            )
        return evidence

    def _find_port_binding_evidence(self, sb_idl, port_name: str) -> list[str]:
        evidence: list[str] = []
        for row in sb_idl.tables["Port_Binding"].rows.values():
            if getattr(row, "logical_port", None) != port_name:
                continue
            evidence.append(
                "port_binding="
                f"{row.uuid} type={getattr(row, 'type', '')} datapath="
                f"{_row_uuid(getattr(row, 'datapath', None))} chassis="
                f"{_row_name(getattr(row, 'chassis', None))}"
            )
        return evidence

    def _find_logical_flow_evidence(self, sb_idl, nb_uuid: str, *tokens: str) -> list[str]:
        uuid_prefix = _uuid_prefix(nb_uuid)
        exact_matches: list[str] = []
        token_matches: list[str] = []
        for row in sb_idl.tables["Logical_Flow"].rows.values():
            external_ids = dict(getattr(row, "external_ids", {}))
            stage_hint = _normalize_uuid(external_ids.get("stage-hint"))
            evidence = (
                f"logical_flow={row.uuid} stage={external_ids.get('stage-name')} "
                f"hint={external_ids.get('stage-hint')} match={getattr(row, 'match', '')}"
            )
            if stage_hint in {nb_uuid, uuid_prefix}:
                exact_matches.append(evidence)
                continue
            haystack = " ".join(
                [
                    str(getattr(row, "match", "")),
                    str(getattr(row, "actions", "")),
                    " ".join(f"{key}={value}" for key, value in external_ids.items()),
                ]
            )
            if any(token in haystack for token in tokens if token):
                token_matches.append(evidence)
        return exact_matches or token_matches

    def _find_openflow_evidence(self, prepared: PreparedProbe) -> list[str]:
        raw = self.ovs_client.dump_openflow_flows(bridge=prepared.bridge)
        if prepared.resolved_resource_type == "acl":
            tokens = [prepared.context["probe_ip"]]
        elif prepared.resolved_resource_type == "nat":
            tokens = [prepared.context["external_ip"], prepared.context["logical_ip"]]
        else:
            return []
        return [
            line.strip()
            for line in raw.splitlines()
            if line.strip() and not line.startswith("NXST_FLOW reply") and any(token in line for token in tokens)
        ]

    def _derive_status(self, result: CanaryProbeResult) -> str:
        required_stages = [result.nb_committed, result.sb_realized]
        if result.openflow_expected:
            required_stages.append(result.openflow_realized)

        if any(stage.status == "failed" for stage in required_stages):
            return "failed"
        if any(stage.status == "timeout" for stage in required_stages):
            return "timeout"
        if result.cleanup.status == "failed":
            return "partial_success"
        return "success"

    def _delta_ms(self, start: float | None, end: float | None) -> float | None:
        if start is None or end is None:
            return None
        return round((end - start) * 1000, 3)

    def _total_latency_ms(
        self,
        openflow_expected: bool,
        sb_seen_at: float | None,
        of_seen_at: float | None,
        start_perf: float,
    ) -> float | None:
        if openflow_expected:
            return _elapsed_ms(start_perf, of_seen_at) if of_seen_at is not None else None
        return _elapsed_ms(start_perf, sb_seen_at) if sb_seen_at is not None else None

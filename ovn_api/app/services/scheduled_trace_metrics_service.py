from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException

from ..config import get_settings
from ..core.ovn_sb import get_ovn_sb_client
from ..models.trace_metrics import (
    ScheduledTraceMetricsSnapshot,
    ScheduledTraceProfileConfigInput,
    ScheduledTraceProfileStatus,
    ScheduledTraceProfilesConfigFile,
)
from ..models.traces import CanaryProbeRequest, CanaryProbeResult, CanaryResourceType
from ..services.topology_service import TopologyService
from .trace_service import CanaryTraceService


_RESOURCE_TYPES_REQUIRING_SWITCH_TARGET = frozenset({"acl", "logical_flow", "logical_switch_port", "logical_port"})
_RESOURCE_TYPES_REQUIRING_ROUTER_TARGET = frozenset({"nat", "nat_rule", "logical_router_port", "subnet"})
_OPENFLOW_ELIGIBLE_RESOURCE_TYPES = frozenset({"acl", "logical_flow", "nat", "nat_rule"})
_RUN_STATUS_CODE = {
    "success": 0,
    "partial_success": 1,
    "timeout": 2,
    "failed": 3,
    "idle": 4,
}
_STAGE_STATUS_CODE = {
    "observed": 0,
    "timeout": 1,
    "failed": 2,
    "skipped": 3,
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="milliseconds")


def _epoch_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


@dataclass(frozen=True)
class _ProfileConfig:
    name: str
    requested_resource_type: CanaryResourceType
    bridge: str
    configured_target_name: str | None
    interval_s: float
    timeout_s: float
    poll_interval_ms: int
    enabled: bool = True


@dataclass
class _ProfileState:
    config: _ProfileConfig
    next_due_monotonic: float = 0.0
    resolved_target_name: str | None = None
    target_resolution_mode: str = "not_required"
    last_status: str = "idle"
    last_error: str | None = None
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_success_at: str | None = None
    run_count: int = 0
    success_count: int = 0
    partial_success_count: int = 0
    timeout_count: int = 0
    failed_count: int = 0
    last_result: CanaryProbeResult | None = None


class ScheduledTraceMetricsService:
    def __init__(
        self,
        *,
        enabled: bool,
        interval_s: float,
        timeout_s: float,
        poll_interval_ms: int,
        default_bridge: str,
        default_switch_target_name: str | None,
        default_router_target_name: str | None,
        profiles_json: str | None,
        profiles_file: str | None,
    ) -> None:
        self.trace_service = CanaryTraceService()
        self.topology_service = TopologyService()
        self.sb_client = get_ovn_sb_client()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.enabled = enabled
        self.default_bridge = default_bridge or "br-int"
        self.default_switch_target_name = default_switch_target_name
        self.default_router_target_name = default_router_target_name
        self.default_interval_s = interval_s
        self.default_timeout_s = timeout_s
        self.default_poll_interval_ms = poll_interval_ms
        self.profiles_json = profiles_json
        self.profiles_file = profiles_file
        self._profiles = [
            _ProfileState(config=profile_config)
            for profile_config in self._load_profile_configs(
                default_interval_s=self.default_interval_s,
                default_timeout_s=self.default_timeout_s,
                default_poll_interval_ms=self.default_poll_interval_ms,
                profiles_json=self.profiles_json,
                profiles_file=self.profiles_file,
            )
        ]
        self._generated_at = _isoformat(_now_utc()) or ""
        self._schedule_initial_runs()

    def start(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="scheduled-trace-metrics-service",
                daemon=True,
            )
            thread = self._thread
        thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None
            self._stop_event.set()
        if thread is not None:
            thread.join(timeout=2.0)

    def get_snapshot(self) -> ScheduledTraceMetricsSnapshot:
        with self._lock:
            return ScheduledTraceMetricsSnapshot(
                generated_at=self._generated_at,
                status="enabled" if self.enabled else "disabled",
                worker_alive=bool(self._thread is not None and self._thread.is_alive()),
                default_bridge=self.default_bridge,
                profiles=[self._build_profile_status(profile) for profile in self._profiles],
            )

    def get_snapshot_or_none(self) -> ScheduledTraceMetricsSnapshot | None:
        return self.get_snapshot()

    def reload(self, *, reload_settings: bool = False) -> ScheduledTraceMetricsSnapshot:
        self.stop()

        if reload_settings:
            get_settings.cache_clear()
            settings = get_settings()
            enabled = settings.scheduled_trace_metrics_enabled
            default_bridge = settings.scheduled_trace_metrics_default_bridge
            default_switch_target_name = settings.scheduled_trace_metrics_default_logical_switch_target_name
            default_router_target_name = settings.scheduled_trace_metrics_default_logical_router_target_name
            default_interval_s = settings.scheduled_trace_metrics_interval_s
            default_timeout_s = settings.scheduled_trace_metrics_timeout_s
            default_poll_interval_ms = settings.scheduled_trace_metrics_poll_interval_ms
            profiles_json = settings.scheduled_trace_metrics_profiles_json
            profiles_file = settings.scheduled_trace_metrics_profiles_file
        else:
            enabled = self.enabled
            default_bridge = self.default_bridge
            default_switch_target_name = self.default_switch_target_name
            default_router_target_name = self.default_router_target_name
            default_interval_s = self.default_interval_s
            default_timeout_s = self.default_timeout_s
            default_poll_interval_ms = self.default_poll_interval_ms
            profiles_json = self.profiles_json
            profiles_file = self.profiles_file

        with self._lock:
            previous_states = {profile.config.name: profile for profile in self._profiles}
            self.enabled = enabled
            self.default_bridge = default_bridge or "br-int"
            self.default_switch_target_name = default_switch_target_name
            self.default_router_target_name = default_router_target_name
            self.default_interval_s = default_interval_s
            self.default_timeout_s = default_timeout_s
            self.default_poll_interval_ms = default_poll_interval_ms
            self.profiles_json = profiles_json
            self.profiles_file = profiles_file
            profile_configs = self._load_profile_configs(
                default_interval_s=self.default_interval_s,
                default_timeout_s=self.default_timeout_s,
                default_poll_interval_ms=self.default_poll_interval_ms,
                profiles_json=self.profiles_json,
                profiles_file=self.profiles_file,
            )
            self._profiles = self._build_profile_states(profile_configs, previous_states=previous_states)
            self._generated_at = _isoformat(_now_utc()) or ""
            self._schedule_initial_runs()

        if self.enabled:
            self.start()
        return self.get_snapshot()

    def append_prometheus_metrics(
        self,
        lines: list[str],
        *,
        append_metric,
        append_optional_metric,
    ) -> None:
        snapshot = self.get_snapshot()
        append_metric(lines, "ovn_api_scheduled_trace_metrics_enabled", 1 if self.enabled else 0)
        append_metric(lines, "ovn_api_scheduled_trace_service_up", 1 if snapshot.worker_alive else 0)

        for profile in snapshot.profiles:
            base_labels = {
                "requested_resource_type": profile.requested_resource_type,
                "profile": profile.profile,
            }
            append_metric(lines, "ovn_api_scheduled_trace_profile_enabled", 1 if profile.enabled else 0, labels=base_labels)
            append_metric(
                lines,
                "ovn_api_scheduled_trace_last_run_status_code",
                _RUN_STATUS_CODE.get(profile.last_status, 99),
                labels=base_labels,
            )
            append_metric(
                lines,
                "ovn_api_scheduled_trace_runs_total",
                profile.run_count,
                labels={**base_labels, "result": "all"},
            )
            append_metric(
                lines,
                "ovn_api_scheduled_trace_runs_total",
                profile.success_count,
                labels={**base_labels, "result": "success"},
            )
            append_metric(
                lines,
                "ovn_api_scheduled_trace_runs_total",
                profile.partial_success_count,
                labels={**base_labels, "result": "partial_success"},
            )
            append_metric(
                lines,
                "ovn_api_scheduled_trace_runs_total",
                profile.timeout_count,
                labels={**base_labels, "result": "timeout"},
            )
            append_metric(
                lines,
                "ovn_api_scheduled_trace_runs_total",
                profile.failed_count,
                labels={**base_labels, "result": "failed"},
            )
            append_metric(
                lines,
                "ovn_api_scheduled_trace_profile_info",
                1,
                labels={
                    **base_labels,
                    "bridge": profile.bridge,
                    "target_name": profile.resolved_target_name or "",
                    "target_resolution_mode": profile.target_resolution_mode,
                },
            )

            last_finished_at_epoch = _epoch_seconds(profile.last_finished_at)
            last_success_at_epoch = _epoch_seconds(profile.last_success_at)
            append_optional_metric(
                lines,
                "ovn_api_scheduled_trace_last_run_timestamp_seconds",
                last_finished_at_epoch,
                labels=base_labels,
            )
            append_optional_metric(
                lines,
                "ovn_api_scheduled_trace_last_success_timestamp_seconds",
                last_success_at_epoch,
                labels=base_labels,
            )
            if last_finished_at_epoch is not None:
                append_metric(
                    lines,
                    "ovn_api_scheduled_trace_last_run_age_seconds",
                    round(max(time.time() - last_finished_at_epoch, 0.0), 3),
                    labels=base_labels,
                )

            if profile.last_result is None:
                continue
            for phase_name, value in self._phase_duration_map(profile.last_result).items():
                append_optional_metric(
                    lines,
                    "ovn_api_scheduled_trace_phase_duration_ms",
                    value,
                    labels={**base_labels, "phase": phase_name},
                )
            for phase_name, status in self._phase_state_map(profile.last_result).items():
                append_metric(
                    lines,
                    "ovn_api_scheduled_trace_phase_state_code",
                    _STAGE_STATUS_CODE.get(status, 99),
                    labels={**base_labels, "phase": phase_name},
                )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            profile = self._next_due_profile()
            if profile is None:
                self._stop_event.wait(0.5)
                continue
            wait_s = max(profile.next_due_monotonic - time.monotonic(), 0.0)
            if self._stop_event.wait(min(wait_s, 0.5)):
                break
            if time.monotonic() < profile.next_due_monotonic:
                continue
            self._execute_profile(profile)

    def _schedule_initial_runs(self) -> None:
        if not self._profiles:
            return
        now = time.monotonic()
        stagger_s = max(self._profiles[0].config.interval_s / max(len(self._profiles), 1), 1.0)
        for index, profile in enumerate(self._profiles):
            profile.next_due_monotonic = now + (index * stagger_s)

    def _next_due_profile(self) -> _ProfileState | None:
        with self._lock:
            enabled_profiles = [profile for profile in self._profiles if profile.config.enabled]
            if not enabled_profiles:
                return None
            return min(enabled_profiles, key=lambda item: item.next_due_monotonic)

    def _execute_profile(self, profile: _ProfileState) -> None:
        config = profile.config
        started_at = _isoformat(_now_utc()) or ""
        with self._lock:
            profile.run_count += 1
            profile.last_started_at = started_at
            profile.last_error = None
            profile.next_due_monotonic = time.monotonic() + config.interval_s
            self._generated_at = started_at

        resolved_target_name, target_resolution_mode, resolution_error = self._resolve_target_name(config)
        request = CanaryProbeRequest(
            resource_type=config.requested_resource_type,
            target_name=resolved_target_name,
            bridge=config.bridge,
            timeout_s=config.timeout_s,
            poll_interval_ms=config.poll_interval_ms,
            expect_openflow=(
                True
                if resolved_target_name is not None and config.requested_resource_type in _OPENFLOW_ELIGIBLE_RESOURCE_TYPES
                else None
            ),
        )

        with self._lock:
            profile.resolved_target_name = resolved_target_name
            profile.target_resolution_mode = target_resolution_mode

        if resolution_error is not None:
            finished_at = _isoformat(_now_utc()) or ""
            with self._lock:
                profile.last_status = "failed"
                profile.last_error = resolution_error
                profile.failed_count += 1
                profile.last_finished_at = finished_at
                self._generated_at = finished_at
            return

        try:
            result = self.trace_service.run_probe(request)
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            finished_at = _isoformat(_now_utc()) or ""
            with self._lock:
                profile.last_status = "failed"
                profile.last_error = detail
                profile.failed_count += 1
                profile.last_finished_at = finished_at
                profile.last_result = None
                self._generated_at = finished_at
            return
        except Exception as exc:  # pragma: no cover - unexpected runtime failure
            finished_at = _isoformat(_now_utc()) or ""
            with self._lock:
                profile.last_status = "failed"
                profile.last_error = f"Unexpected scheduled trace error: {type(exc).__name__}: {exc}"
                profile.failed_count += 1
                profile.last_finished_at = finished_at
                profile.last_result = None
                self._generated_at = finished_at
            return

        finished_at = result.finished_at or (_isoformat(_now_utc()) or "")
        with self._lock:
            profile.last_status = result.status
            profile.last_error = None
            profile.last_finished_at = finished_at
            profile.last_result = result.model_copy(deep=True)
            if result.status == "success":
                profile.success_count += 1
                profile.last_success_at = finished_at
            elif result.status == "partial_success":
                profile.partial_success_count += 1
                profile.last_success_at = finished_at
            elif result.status == "timeout":
                profile.timeout_count += 1
            else:
                profile.failed_count += 1
            self._generated_at = finished_at

    def _resolve_target_name(self, config: _ProfileConfig) -> tuple[str | None, str, str | None]:
        if config.requested_resource_type in _RESOURCE_TYPES_REQUIRING_SWITCH_TARGET:
            if config.configured_target_name:
                return config.configured_target_name, "configured", None
            if self.default_switch_target_name:
                return self.default_switch_target_name, "configured", None
            target_name = self._auto_select_switch_target()
            if target_name is None:
                return None, "unresolved", "No logical switch target could be auto-selected for the scheduled probe."
            return target_name, "auto", None

        if config.requested_resource_type in _RESOURCE_TYPES_REQUIRING_ROUTER_TARGET:
            if config.configured_target_name:
                return config.configured_target_name, "configured", None
            if self.default_router_target_name:
                return self.default_router_target_name, "configured", None
            target_name = self._auto_select_router_target()
            if target_name is None:
                return None, "unresolved", "No logical router target could be auto-selected for the scheduled probe."
            return target_name, "auto", None

        return None, "not_required", None

    def _auto_select_switch_target(self) -> str | None:
        switches = self.topology_service.list_switches()
        if not switches:
            return None
        realized_switch_names = self._realized_datapath_names(expected_type="logical-switch")
        candidates = [
            switch
            for switch in switches
            if switch.name and (switch.name in realized_switch_names or not realized_switch_names)
        ]
        if not candidates:
            candidates = [switch for switch in switches if switch.name]
        if not candidates:
            return None
        best = max(candidates, key=lambda item: (item.port_count, item.acl_count, item.load_balancer_count, item.name))
        return best.name

    def _auto_select_router_target(self) -> str | None:
        routers = self.topology_service.list_routers()
        if not routers:
            return None
        realized_router_names = self._realized_datapath_names(expected_type="logical-router")
        candidates = [
            router
            for router in routers
            if router.name and (router.name in realized_router_names or not realized_router_names)
        ]
        if not candidates:
            candidates = [router for router in routers if router.name]
        if not candidates:
            return None
        best = max(candidates, key=lambda item: (item.port_count, item.nat_count, item.static_route_count, item.name))
        return best.name

    def _realized_datapath_names(self, *, expected_type: str) -> set[str]:
        try:
            sb_idl = self.sb_client.get_idl()
        except HTTPException:
            return set()
        names: set[str] = set()
        for row in sb_idl.tables["Datapath_Binding"].rows.values():
            row_type = getattr(row, "type", None)
            if str(row_type) != expected_type:
                continue
            external_ids = dict(getattr(row, "external_ids", {}))
            name = external_ids.get("name")
            if name:
                names.add(str(name))
        return names

    def _build_profile_status(self, profile: _ProfileState) -> ScheduledTraceProfileStatus:
        config = profile.config
        return ScheduledTraceProfileStatus(
            profile=config.name,
            requested_resource_type=config.requested_resource_type,
            bridge=config.bridge,
            configured_target_name=config.configured_target_name,
            resolved_target_name=profile.resolved_target_name,
            target_resolution_mode=profile.target_resolution_mode,
            interval_s=config.interval_s,
            timeout_s=config.timeout_s,
            poll_interval_ms=config.poll_interval_ms,
            enabled=self.enabled and config.enabled,
            last_status=profile.last_status,
            last_error=profile.last_error,
            last_started_at=profile.last_started_at,
            last_finished_at=profile.last_finished_at,
            last_success_at=profile.last_success_at,
            run_count=profile.run_count,
            success_count=profile.success_count,
            partial_success_count=profile.partial_success_count,
            timeout_count=profile.timeout_count,
            failed_count=profile.failed_count,
            last_result=profile.last_result.model_copy(deep=True) if profile.last_result is not None else None,
        )

    def _load_profile_configs(
        self,
        *,
        default_interval_s: float,
        default_timeout_s: float,
        default_poll_interval_ms: int,
        profiles_json: str | None,
        profiles_file: str | None,
    ) -> list[_ProfileConfig]:
        profile_inputs, source_was_provided = self._load_profile_inputs(
            profiles_json=profiles_json,
            profiles_file=profiles_file,
        )
        if not source_was_provided and not profile_inputs:
            return self._default_profile_configs(
                default_interval_s=default_interval_s,
                default_timeout_s=default_timeout_s,
                default_poll_interval_ms=default_poll_interval_ms,
            )

        profile_names: set[str] = set()
        profile_configs: list[_ProfileConfig] = []
        for profile_input in profile_inputs:
            if profile_input.name in profile_names:
                raise HTTPException(
                    status_code=500,
                    detail=f"Duplicate scheduled trace profile name {profile_input.name!r}.",
                )
            profile_names.add(profile_input.name)
            profile_configs.append(
                _ProfileConfig(
                    name=profile_input.name,
                    requested_resource_type=profile_input.resource_type,
                    configured_target_name=profile_input.target_name,
                    bridge=profile_input.bridge or self.default_bridge,
                    interval_s=profile_input.interval_s or default_interval_s,
                    timeout_s=profile_input.timeout_s or default_timeout_s,
                    poll_interval_ms=profile_input.poll_interval_ms or default_poll_interval_ms,
                    enabled=profile_input.enabled,
                )
            )
        return profile_configs

    def _load_profile_inputs(
        self,
        *,
        profiles_json: str | None,
        profiles_file: str | None,
    ) -> tuple[list[ScheduledTraceProfileConfigInput], bool]:
        raw_payload: object | None = None
        source = "default"
        source_was_provided = False

        if profiles_file:
            try:
                raw_payload = json.loads(Path(profiles_file).expanduser().read_text())
            except FileNotFoundError as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"Scheduled trace profiles file {profiles_file!r} was not found.",
                ) from exc
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"Scheduled trace profiles file {profiles_file!r} is not valid JSON: {exc}",
                ) from exc
            source = f"file:{profiles_file}"
            source_was_provided = True
        elif profiles_json:
            try:
                raw_payload = json.loads(profiles_json)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"SCHEDULED_TRACE_METRICS_PROFILES_JSON is not valid JSON: {exc}",
                ) from exc
            source = "env:SCHEDULED_TRACE_METRICS_PROFILES_JSON"
            source_was_provided = True

        if raw_payload is None:
            return [], source_was_provided

        try:
            if isinstance(raw_payload, dict):
                config_file = ScheduledTraceProfilesConfigFile.model_validate(raw_payload)
                return config_file.profiles, source_was_provided
            if isinstance(raw_payload, list):
                return [ScheduledTraceProfileConfigInput.model_validate(item) for item in raw_payload], source_was_provided
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to validate scheduled trace profiles from {source}: {type(exc).__name__}: {exc}",
            ) from exc

        raise HTTPException(
            status_code=500,
            detail=(
                "Scheduled trace profiles must be either a JSON list or an object with a 'profiles' field. "
                f"source={source}"
            ),
        )

    def _default_profile_configs(
        self,
        *,
        default_interval_s: float,
        default_timeout_s: float,
        default_poll_interval_ms: int,
        ) -> list[_ProfileConfig]:
        return [
            _ProfileConfig(
                name="logical_flow_default",
                requested_resource_type="logical_flow",
                configured_target_name=self.default_switch_target_name,
                bridge=self.default_bridge,
                interval_s=default_interval_s,
                timeout_s=default_timeout_s,
                poll_interval_ms=default_poll_interval_ms,
            ),
            _ProfileConfig(
                name="logical_switch_default",
                requested_resource_type="logical_switch",
                configured_target_name=None,
                bridge=self.default_bridge,
                interval_s=default_interval_s,
                timeout_s=default_timeout_s,
                poll_interval_ms=default_poll_interval_ms,
            ),
            _ProfileConfig(
                name="logical_router_default",
                requested_resource_type="logical_router",
                configured_target_name=None,
                bridge=self.default_bridge,
                interval_s=default_interval_s,
                timeout_s=default_timeout_s,
                poll_interval_ms=default_poll_interval_ms,
            ),
        ]

    def _build_profile_states(
        self,
        profile_configs: list[_ProfileConfig],
        *,
        previous_states: dict[str, _ProfileState],
    ) -> list[_ProfileState]:
        states: list[_ProfileState] = []
        for profile_config in profile_configs:
            previous_state = previous_states.get(profile_config.name)
            if previous_state is not None and self._can_reuse_state(previous_state.config, profile_config):
                states.append(
                    _ProfileState(
                        config=profile_config,
                        resolved_target_name=previous_state.resolved_target_name,
                        target_resolution_mode=previous_state.target_resolution_mode,
                        last_status=previous_state.last_status,
                        last_error=previous_state.last_error,
                        last_started_at=previous_state.last_started_at,
                        last_finished_at=previous_state.last_finished_at,
                        last_success_at=previous_state.last_success_at,
                        run_count=previous_state.run_count,
                        success_count=previous_state.success_count,
                        partial_success_count=previous_state.partial_success_count,
                        timeout_count=previous_state.timeout_count,
                        failed_count=previous_state.failed_count,
                        last_result=previous_state.last_result.model_copy(deep=True)
                        if previous_state.last_result is not None
                        else None,
                    )
                )
                continue
            states.append(_ProfileState(config=profile_config))
        return states

    def _can_reuse_state(self, old_config: _ProfileConfig, new_config: _ProfileConfig) -> bool:
        return (
            old_config.requested_resource_type == new_config.requested_resource_type
            and old_config.bridge == new_config.bridge
            and old_config.configured_target_name == new_config.configured_target_name
        )

    def _phase_duration_map(self, result: CanaryProbeResult) -> dict[str, float | None]:
        return {
            "command": result.command_latency_ms,
            "nb_committed": result.nb_committed.latency_ms,
            "sb_realized": result.sb_realized.latency_ms,
            "openflow_realized": result.openflow_realized.latency_ms,
            "nb_to_sb": result.nb_to_sb_latency_ms,
            "sb_to_openflow": result.sb_to_openflow_latency_ms,
            "total": result.total_latency_ms,
        }

    def _phase_state_map(self, result: CanaryProbeResult) -> dict[str, str]:
        return {
            "nb_committed": result.nb_committed.status,
            "sb_realized": result.sb_realized.status,
            "openflow_realized": result.openflow_realized.status,
            "cleanup": result.cleanup.status,
        }


@lru_cache(maxsize=1)
def get_scheduled_trace_metrics_service() -> ScheduledTraceMetricsService:
    settings = get_settings()
    return ScheduledTraceMetricsService(
        enabled=settings.scheduled_trace_metrics_enabled,
        interval_s=settings.scheduled_trace_metrics_interval_s,
        timeout_s=settings.scheduled_trace_metrics_timeout_s,
        poll_interval_ms=settings.scheduled_trace_metrics_poll_interval_ms,
        default_bridge=settings.scheduled_trace_metrics_default_bridge,
        default_switch_target_name=settings.scheduled_trace_metrics_default_logical_switch_target_name,
        default_router_target_name=settings.scheduled_trace_metrics_default_logical_router_target_name,
        profiles_json=settings.scheduled_trace_metrics_profiles_json,
        profiles_file=settings.scheduled_trace_metrics_profiles_file,
    )

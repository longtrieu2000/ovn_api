from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import HTTPException

from ..config import Settings, get_settings
from ..models import CpuHistoryPoint, CpuSnapshot, CpuSpike, CpuUsage, ProcessCpuSample, SoftirqDelta, ThreadCpuSample, ThreadGroupSample
from .procfs import CpuStat, ProcfsReader, SchedEntityStat


@dataclass(frozen=True)
class Usage:
    total_pct: float
    user_pct: float
    system_pct: float


@dataclass(frozen=True)
class ProcessIdentity:
    component: str
    category: str
    label: str
    is_kernel: bool


@dataclass(frozen=True)
class ThreadRecord:
    pid: int
    tid: int
    process_name: str
    process_component: str
    process_category: str
    process_label: str
    thread_name: str
    thread_group: str
    state: str
    wchan: str | None
    cpu: Usage


@dataclass(frozen=True)
class ProcessRecord:
    pid: int
    process_name: str
    component: str
    category: str
    label: str
    cmdline: str
    thread_count: int
    cpu: Usage
    threads: tuple[ThreadRecord, ...]


@dataclass(frozen=True)
class GroupRecord:
    component: str
    category: str
    thread_group: str
    threads: int
    cpu: Usage


@dataclass(frozen=True)
class SoftirqRecord:
    name: str
    total_delta: int
    per_cpu_delta: tuple[int, ...]


@dataclass(frozen=True)
class SnapshotState:
    generated_at: datetime
    elapsed_s: float
    warmup: bool
    cpu_count: int
    host_cpu_pct: float | None
    loadavg: tuple[float, float, float]
    processes: tuple[ProcessRecord, ...]
    threads: tuple[ThreadRecord, ...]
    groups: tuple[GroupRecord, ...]
    softirqs: tuple[SoftirqRecord, ...]


class CpuMonitorService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.procfs = ProcfsReader(self.settings.proc_root)
        self.interval_s = self.settings.sample_interval_s
        self.cpu_count = os.cpu_count() or 1
        self.clock_ticks = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        self.monitored_processes = {name.lower() for name in self.settings.user_process_names}

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._snapshot: SnapshotState | None = None
        self._history: deque[CpuHistoryPoint] = deque(maxlen=self.settings.history_size)
        self._last_error: str | None = None

        self._prev_ts: float | None = None
        self._prev_system_cpu: CpuStat | None = None
        self._prev_softirqs: dict[str, list[int]] | None = None
        self._prev_process_times: dict[tuple[int, int], tuple[int, int]] = {}
        self._prev_thread_times: dict[tuple[int, int, int], tuple[int, int]] = {}

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="ovn-cpu-monitor", daemon=True)

        self._refresh_safely()
        assert self._thread is not None
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None
            self._stop_event.set()

        if thread is not None:
            thread.join(timeout=self.interval_s + 1.0)

    def collect_now(self) -> SnapshotState:
        state = self._collect_snapshot()
        history_point = self._build_history_point(state)
        with self._lock:
            self._snapshot = state
            self._history.append(history_point)
            self._last_error = None
        return state

    def get_snapshot(self, *, threads_per_component: int, top_threads: int) -> CpuSnapshot:
        state = self._require_snapshot()
        return self._build_snapshot_model(
            state,
            threads_per_component=threads_per_component,
            top_threads=top_threads,
        )

    def get_history(self, *, limit: int) -> list[CpuHistoryPoint]:
        with self._lock:
            history = list(self._history)
            last_error = self._last_error
        if not history:
            raise HTTPException(
                status_code=503,
                detail=last_error or "CPU monitor has not produced a snapshot yet.",
            )
        return history[-limit:]

    def get_threads(
        self,
        *,
        component: str | None,
        thread_group: str | None,
        limit: int,
        min_cpu_pct: float,
    ) -> list[ThreadCpuSample]:
        state = self._require_snapshot()
        component_filter = component.lower() if component else None
        group_filter = thread_group.lower() if thread_group else None

        selected = []
        for record in state.threads:
            if component_filter and record.process_component.lower() != component_filter:
                continue
            if group_filter and record.thread_group.lower() != group_filter:
                continue
            if record.cpu.total_pct < min_cpu_pct:
                continue
            selected.append(self._thread_model(record))
            if len(selected) >= limit:
                break
        return selected

    def find_spikes(self, *, component: str | None, threshold_pct: float, limit: int) -> list[CpuSpike]:
        with self._lock:
            history = list(self._history)
            last_error = self._last_error
        if not history:
            raise HTTPException(
                status_code=503,
                detail=last_error or "CPU monitor has not produced any history yet.",
            )

        component_filter = component.lower() if component else None
        spikes: list[CpuSpike] = []
        for point in reversed(history):
            for process in point.components:
                if component_filter and process.component.lower() != component_filter:
                    continue
                if process.cpu.total_pct < threshold_pct:
                    continue
                spikes.append(
                    CpuSpike(
                        generated_at=point.generated_at,
                        component=process.component,
                        pid=process.pid,
                        cpu=process.cpu,
                        hot_threads=process.hot_threads[:3],
                    )
                )
                if len(spikes) >= limit:
                    return spikes
        return spikes

    def get_health_snapshot(self) -> dict[str, object]:
        with self._lock:
            snapshot = self._snapshot
            history_size = len(self._history)
            running = self._thread is not None and self._thread.is_alive()

        return {
            "collector_running": running,
            "snapshot_ready": snapshot is not None,
            "history_size": history_size,
            "sample_interval_s": self.interval_s,
            "last_generated_at": snapshot.generated_at.isoformat() if snapshot else None,
        }

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_s):
            self._refresh_safely()

    def _refresh_safely(self) -> None:
        try:
            self.collect_now()
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            with self._lock:
                self._last_error = f"{type(exc).__name__}: {exc}"

    def _collect_snapshot(self) -> SnapshotState:
        now = time.monotonic()
        generated_at = datetime.now(timezone.utc)
        elapsed_s = max((now - self._prev_ts) if self._prev_ts is not None else 0.0, 0.0)
        warmup = self._prev_ts is None

        system_cpu = self.procfs.read_system_cpu()
        softirqs = self.procfs.read_softirqs(self.settings.softirq_names)
        loadavg = self.procfs.read_loadavg()

        next_process_times: dict[tuple[int, int], tuple[int, int]] = {}
        next_thread_times: dict[tuple[int, int, int], tuple[int, int]] = {}

        processes: list[ProcessRecord] = []
        all_threads: list[ThreadRecord] = []

        for pid in self.procfs.list_pids():
            try:
                process_stat = self.procfs.read_process_stat(pid)
                cmdline = self.procfs.read_cmdline(pid)
            except OSError:
                continue
            except ValueError:
                continue

            identity = self._classify_process(process_stat, cmdline)
            if identity is None:
                continue

            process_usage = self._calculate_usage(
                previous=self._prev_process_times.get((pid, process_stat.starttime)),
                utime=process_stat.utime,
                stime=process_stat.stime,
                elapsed_s=elapsed_s,
            )
            next_process_times[(pid, process_stat.starttime)] = (process_stat.utime, process_stat.stime)

            if identity.is_kernel:
                thread_group = self._classify_thread_group(process_stat.comm, pid, pid, True)
                thread = ThreadRecord(
                    pid=pid,
                    tid=pid,
                    process_name=process_stat.comm,
                    process_component=identity.component,
                    process_category=identity.category,
                    process_label=identity.label,
                    thread_name=process_stat.comm,
                    thread_group=thread_group,
                    state=process_stat.state,
                    wchan=self.procfs.read_wchan(pid),
                    cpu=process_usage,
                )
                all_threads.append(thread)
                processes.append(
                    ProcessRecord(
                        pid=pid,
                        process_name=process_stat.comm,
                        component=identity.component,
                        category=identity.category,
                        label=identity.label,
                        cmdline=cmdline,
                        thread_count=1,
                        cpu=process_usage,
                        threads=(thread,),
                    )
                )
                continue

            threads: list[ThreadRecord] = []
            try:
                tids = self.procfs.list_task_ids(pid)
            except OSError:
                tids = [pid]

            for tid in tids:
                try:
                    task_stat = self.procfs.read_task_stat(pid, tid)
                except (OSError, ValueError):
                    continue

                thread_usage = self._calculate_usage(
                    previous=self._prev_thread_times.get((pid, tid, task_stat.starttime)),
                    utime=task_stat.utime,
                    stime=task_stat.stime,
                    elapsed_s=elapsed_s,
                )
                next_thread_times[(pid, tid, task_stat.starttime)] = (task_stat.utime, task_stat.stime)

                threads.append(
                    ThreadRecord(
                        pid=pid,
                        tid=tid,
                        process_name=process_stat.comm,
                        process_component=identity.component,
                        process_category=identity.category,
                        process_label=identity.label,
                        thread_name=task_stat.comm,
                        thread_group=self._classify_thread_group(task_stat.comm, pid, tid, False),
                        state=task_stat.state,
                        wchan=self.procfs.read_wchan(pid, tid),
                        cpu=thread_usage,
                    )
                )

            if not threads:
                threads.append(
                    ThreadRecord(
                        pid=pid,
                        tid=pid,
                        process_name=process_stat.comm,
                        process_component=identity.component,
                        process_category=identity.category,
                        process_label=identity.label,
                        thread_name=process_stat.comm,
                        thread_group="main",
                        state=process_stat.state,
                        wchan=self.procfs.read_wchan(pid),
                        cpu=process_usage,
                    )
                )

            threads.sort(key=lambda item: (-item.cpu.total_pct, item.tid))
            all_threads.extend(threads)
            processes.append(
                ProcessRecord(
                    pid=pid,
                    process_name=process_stat.comm,
                    component=identity.component,
                    category=identity.category,
                    label=identity.label,
                    cmdline=cmdline,
                    thread_count=max(process_stat.num_threads, len(threads)),
                    cpu=process_usage,
                    threads=tuple(threads),
                )
            )

        all_threads.sort(key=lambda item: (-item.cpu.total_pct, item.pid, item.tid))
        processes.sort(key=lambda item: (-item.cpu.total_pct, item.component, item.pid))
        groups = self._aggregate_groups(all_threads)
        softirq_records = self._compute_softirq_records(softirqs)
        host_cpu_pct = self._compute_host_cpu_pct(system_cpu)

        self._prev_ts = now
        self._prev_system_cpu = system_cpu
        self._prev_softirqs = softirqs
        self._prev_process_times = next_process_times
        self._prev_thread_times = next_thread_times

        return SnapshotState(
            generated_at=generated_at,
            elapsed_s=elapsed_s,
            warmup=warmup,
            cpu_count=self.cpu_count,
            host_cpu_pct=host_cpu_pct,
            loadavg=loadavg,
            processes=tuple(processes),
            threads=tuple(all_threads),
            groups=tuple(groups),
            softirqs=tuple(softirq_records),
        )

    def _classify_process(self, process_stat: SchedEntityStat, cmdline: str) -> ProcessIdentity | None:
        comm = process_stat.comm.lower()
        lower_cmd = cmdline.lower()

        if self.settings.enable_kernel_threads and self._is_kernel_datapath_thread(process_stat.comm, cmdline):
            return ProcessIdentity(
                component="kernel-datapath",
                category="kernel",
                label=process_stat.comm,
                is_kernel=True,
            )

        if comm not in self.monitored_processes:
            return None

        if comm == "ovs-vswitchd":
            return ProcessIdentity("ovs-vswitchd", "datapath", "ovs-vswitchd", False)
        if comm == "ovn-controller":
            return ProcessIdentity("ovn-controller", "control-plane", "ovn-controller", False)
        if comm == "ovn-controller-vtep":
            return ProcessIdentity("ovn-controller-vtep", "control-plane", "ovn-controller-vtep", False)
        if comm == "ovn-northd":
            return ProcessIdentity("ovn-northd", "control-plane", "ovn-northd", False)
        if comm == "ovsdb-server":
            if self._matches_any(lower_cmd, ("ovnsb_db", "ovnsb", "ovn_southbound", "ovn-southbound", "sb.db")):
                return ProcessIdentity("ovn-sb-db", "ovsdb", "ovn-sb-db", False)
            if self._matches_any(lower_cmd, ("ovnnb_db", "ovnnb", "ovn_northbound", "ovn-northbound", "nb.db")):
                return ProcessIdentity("ovn-nb-db", "ovsdb", "ovn-nb-db", False)
            if self._matches_any(lower_cmd, ("sb-relay", "relay")):
                return ProcessIdentity("ovn-sb-relay", "ovsdb", "ovn-sb-relay", False)
            if self._matches_any(lower_cmd, ("conf.db", "open_vswitch", "openvswitch")):
                return ProcessIdentity("ovs-db", "ovsdb", "ovs-db", False)
            return ProcessIdentity("ovsdb-server", "ovsdb", "ovsdb-server", False)

        return ProcessIdentity(process_stat.comm, "other", process_stat.comm, False)

    def _classify_thread_group(self, thread_name: str, pid: int, tid: int, is_kernel: bool) -> str:
        lower = thread_name.lower()

        if is_kernel:
            if lower.startswith("ksoftirqd/"):
                return "ksoftirqd"
            if lower.startswith("irq/"):
                return "irq"
            if lower.startswith("napi/"):
                return "napi"
            return "kernel-other"

        if pid == tid:
            return "main"
        if lower == "handler":
            return "handler"
        if lower == "revalidator":
            return "revalidator"
        if lower.startswith("pmd-"):
            return "pmd"
        if lower == "urcu":
            return "urcu"
        if lower == "monitor":
            return "monitor"
        if lower == "ovn_pinctrl":
            return "pinctrl"
        if lower == "ovn_statctrl":
            return "statctrl"
        if lower == "compaction":
            return "compaction"
        if lower == "log_fsync":
            return "log_fsync"
        if lower == "dpdk_offload":
            return "dpdk_offload"
        if lower == "dpdk_watchdog":
            return "dpdk_watchdog"
        if lower == "ovs_vhost":
            return "ovs_vhost"
        if lower == "ct_clean":
            return "ct_clean"
        if lower == "ipf_clean":
            return "ipf_clean"
        return "other"

    def _aggregate_groups(self, threads: list[ThreadRecord]) -> list[GroupRecord]:
        group_totals: dict[tuple[str, str, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
        for thread in threads:
            key = (thread.process_component, thread.process_category, thread.thread_group)
            totals = group_totals[key]
            totals[0] += thread.cpu.total_pct
            totals[1] += thread.cpu.user_pct
            totals[2] += thread.cpu.system_pct
            totals[3] += 1.0

        records = [
            GroupRecord(
                component=component,
                category=category,
                thread_group=thread_group,
                threads=int(values[3]),
                cpu=Usage(total_pct=values[0], user_pct=values[1], system_pct=values[2]),
            )
            for (component, category, thread_group), values in group_totals.items()
        ]
        records.sort(key=lambda item: (-item.cpu.total_pct, item.component, item.thread_group))
        return records

    def _compute_softirq_records(self, softirqs: dict[str, list[int]]) -> list[SoftirqRecord]:
        records: list[SoftirqRecord] = []
        previous = self._prev_softirqs or {}
        for name in self.settings.softirq_names:
            current_values = softirqs.get(name, [])
            previous_values = previous.get(name, [])
            delta = []
            for index, value in enumerate(current_values):
                prev_value = previous_values[index] if index < len(previous_values) else value
                delta.append(max(0, value - prev_value))
            records.append(
                SoftirqRecord(
                    name=name,
                    total_delta=sum(delta),
                    per_cpu_delta=tuple(delta),
                )
            )
        return records

    def _compute_host_cpu_pct(self, current: CpuStat) -> float | None:
        previous = self._prev_system_cpu
        if previous is None:
            return None
        total_delta = current.total - previous.total
        busy_delta = current.busy - previous.busy
        if total_delta <= 0:
            return None
        return max(0.0, busy_delta / total_delta * 100.0)

    def _calculate_usage(
        self,
        *,
        previous: tuple[int, int] | None,
        utime: int,
        stime: int,
        elapsed_s: float,
    ) -> Usage:
        if previous is None or elapsed_s <= 0:
            return Usage(total_pct=0.0, user_pct=0.0, system_pct=0.0)

        delta_user = max(0, utime - previous[0])
        delta_system = max(0, stime - previous[1])
        scale = 100.0 / (self.clock_ticks * elapsed_s)
        user_pct = delta_user * scale
        system_pct = delta_system * scale
        return Usage(
            total_pct=user_pct + system_pct,
            user_pct=user_pct,
            system_pct=system_pct,
        )

    def _build_snapshot_model(
        self,
        state: SnapshotState,
        *,
        threads_per_component: int,
        top_threads: int,
    ) -> CpuSnapshot:
        visible_processes = self._visible_processes(state.processes)
        visible_threads = self._visible_threads(state.threads)
        visible_groups = self._visible_groups(state.groups)
        return CpuSnapshot(
            generated_at=state.generated_at,
            elapsed_s=round(state.elapsed_s, 3),
            warmup=state.warmup,
            cpu_count=state.cpu_count,
            host_cpu_pct=self._round_float(state.host_cpu_pct),
            loadavg=[round(value, 3) for value in state.loadavg],
            components=[
                self._process_model(record, hot_thread_limit=threads_per_component)
                for record in visible_processes
            ],
            top_threads=[self._thread_model(record) for record in visible_threads[:top_threads]],
            thread_groups=[self._group_model(record) for record in visible_groups],
            softirqs=[self._softirq_model(record) for record in state.softirqs],
        )

    def _build_history_point(self, state: SnapshotState) -> CpuHistoryPoint:
        hot_threads = min(self.settings.default_top_threads, 10)
        per_component_threads = min(self.settings.default_threads_per_component, 3)
        visible_processes = self._visible_processes(state.processes)
        visible_threads = self._visible_threads(state.threads)
        return CpuHistoryPoint(
            generated_at=state.generated_at,
            elapsed_s=round(state.elapsed_s, 3),
            warmup=state.warmup,
            host_cpu_pct=self._round_float(state.host_cpu_pct),
            components=[
                self._process_model(record, hot_thread_limit=per_component_threads)
                for record in visible_processes
            ],
            top_threads=[self._thread_model(record) for record in visible_threads[:hot_threads]],
            softirqs=[self._softirq_model(record) for record in state.softirqs],
        )

    def _process_model(self, record: ProcessRecord, *, hot_thread_limit: int) -> ProcessCpuSample:
        return ProcessCpuSample(
            pid=record.pid,
            process_name=record.process_name,
            component=record.component,
            category=record.category,
            label=record.label,
            cmdline=record.cmdline,
            thread_count=record.thread_count,
            cpu=self._usage_model(record.cpu),
            hot_threads=[self._thread_model(thread) for thread in record.threads[:hot_thread_limit]],
        )

    def _thread_model(self, record: ThreadRecord) -> ThreadCpuSample:
        return ThreadCpuSample(
            pid=record.pid,
            tid=record.tid,
            process_name=record.process_name,
            process_component=record.process_component,
            process_category=record.process_category,
            process_label=record.process_label,
            thread_name=record.thread_name,
            thread_group=record.thread_group,
            state=record.state,
            wchan=record.wchan,
            cpu=self._usage_model(record.cpu),
        )

    def _group_model(self, record: GroupRecord) -> ThreadGroupSample:
        return ThreadGroupSample(
            component=record.component,
            category=record.category,
            thread_group=record.thread_group,
            threads=record.threads,
            cpu=self._usage_model(record.cpu),
        )

    def _softirq_model(self, record: SoftirqRecord) -> SoftirqDelta:
        return SoftirqDelta(
            name=record.name,
            total_delta=record.total_delta,
            per_cpu_delta=list(record.per_cpu_delta),
        )

    def _usage_model(self, usage: Usage) -> CpuUsage:
        return CpuUsage(
            total_pct=round(usage.total_pct, 3),
            user_pct=round(usage.user_pct, 3),
            system_pct=round(usage.system_pct, 3),
        )

    def _require_snapshot(self) -> SnapshotState:
        with self._lock:
            snapshot = self._snapshot
            last_error = self._last_error
        if snapshot is None:
            raise HTTPException(
                status_code=503,
                detail=last_error or "CPU monitor has not produced a snapshot yet.",
            )
        return snapshot

    @staticmethod
    def _round_float(value: float | None) -> float | None:
        return round(value, 3) if value is not None else None

    @staticmethod
    def _matches_any(value: str, patterns: tuple[str, ...]) -> bool:
        return any(pattern in value for pattern in patterns)

    @staticmethod
    def _is_kernel_datapath_thread(comm: str, cmdline: str) -> bool:
        lower = comm.lower()
        if cmdline:
            return False
        return (
            lower.startswith("ksoftirqd/")
            or lower.startswith("irq/")
            or lower.startswith("napi/")
        )

    @staticmethod
    def _visible_processes(processes: tuple[ProcessRecord, ...]) -> list[ProcessRecord]:
        return [
            process
            for process in processes
            if process.category != "kernel" or process.cpu.total_pct > 0.0
        ]

    @staticmethod
    def _visible_threads(threads: tuple[ThreadRecord, ...]) -> list[ThreadRecord]:
        return [thread for thread in threads if thread.cpu.total_pct > 0.0]

    @staticmethod
    def _visible_groups(groups: tuple[GroupRecord, ...]) -> list[GroupRecord]:
        return [
            group
            for group in groups
            if group.category != "kernel" or group.cpu.total_pct > 0.0
        ]


@lru_cache(maxsize=1)
def get_cpu_monitor_service() -> CpuMonitorService:
    return CpuMonitorService(settings=get_settings())

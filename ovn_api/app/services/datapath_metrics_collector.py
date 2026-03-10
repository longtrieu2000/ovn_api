from __future__ import annotations

import re
import threading
from functools import lru_cache

from fastapi import HTTPException

from ..config import get_settings
from ..core.ovs import get_ovs_command_client
from ..models.metrics import DatapathMetrics


LOOKUPS_RE = re.compile(r"^\s*lookups:\s*hit:(?P<hit>\d+)\s+missed:(?P<missed>\d+)\s+lost:(?P<lost>\d+)\s*$")
FLOWS_RE = re.compile(r"^\s*flows:\s*(?P<flows>\d+)\s*$")
MASKS_RE = re.compile(
    r"^\s*masks:\s*hit:(?P<hit>\d+)\s+total:(?P<total>\d+)\s+hit/pkt:(?P<hit_per_pkt>[0-9.]+)\s*$"
)
CACHE_RE = re.compile(r"^\s*cache:\s*hit:(?P<hit>\d+)\s+hit-rate:(?P<hit_rate>[0-9.]+)%\s*$")


def _parse_dpctl_show(raw: str) -> DatapathMetrics:
    lookups_hit = 0
    lookups_missed = 0
    lookups_lost = 0
    datapath_flows = 0
    total_mask_hits = 0
    total_cache_hits = 0
    has_mask_stats = False
    has_cache_stats = False
    has_datapath_stats = False

    for line in raw.splitlines():
        lookup_match = LOOKUPS_RE.match(line)
        if lookup_match:
            lookups_hit += int(lookup_match.group("hit"))
            lookups_missed += int(lookup_match.group("missed"))
            lookups_lost += int(lookup_match.group("lost"))
            has_datapath_stats = True
            continue

        flows_match = FLOWS_RE.match(line)
        if flows_match:
            datapath_flows += int(flows_match.group("flows"))
            has_datapath_stats = True
            continue

        masks_match = MASKS_RE.match(line)
        if masks_match:
            total_mask_hits += int(masks_match.group("hit"))
            has_mask_stats = True
            continue

        cache_match = CACHE_RE.match(line)
        if cache_match:
            total_cache_hits += int(cache_match.group("hit"))
            has_cache_stats = True
            continue

    if not has_datapath_stats:
        raise HTTPException(
            status_code=500,
            detail="Failed to parse datapath stats from 'ovs-appctl dpctl/show' output.",
        )

    total_packets = lookups_hit + lookups_missed
    return DatapathMetrics(
        datapath_flows=datapath_flows,
        lookups_hit=lookups_hit,
        lookups_missed=lookups_missed,
        lookups_lost=lookups_lost,
        cache_hit_rate=round(total_cache_hits / total_packets * 100, 3)
        if has_cache_stats and total_packets
        else None,
        mask_hit_per_pkt=round(total_mask_hits / total_packets, 3)
        if has_mask_stats and total_packets
        else None,
    )


class DatapathMetricsCollector:
    def __init__(self, interval_s: float) -> None:
        self.interval_s = max(interval_s, 1.0)
        self.ovs_client = get_ovs_command_client()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._snapshot: DatapathMetrics | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="datapath-metrics-collector",
                daemon=True,
            )

        self._refresh_safely()
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None
            self._stop_event.set()

        if thread is not None:
            thread.join(timeout=self.interval_s + 1.0)

    def get_snapshot(self) -> DatapathMetrics:
        with self._lock:
            if self._snapshot is not None:
                return self._snapshot
            last_error = self._last_error

        raise HTTPException(
            status_code=503,
            detail=last_error or "Datapath metrics collector has not produced a snapshot yet.",
        )

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_s):
            self._refresh_safely()

    def _refresh_safely(self) -> None:
        try:
            snapshot = self._collect()
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            with self._lock:
                self._last_error = detail
            return
        except Exception as exc:  # pragma: no cover - unexpected runtime failure
            with self._lock:
                self._last_error = f"Unexpected datapath metrics collection error: {type(exc).__name__}: {exc}"
            return

        with self._lock:
            self._snapshot = snapshot
            self._last_error = None

    def _collect(self) -> DatapathMetrics:
        raw = self.ovs_client.show_dpctl()
        return _parse_dpctl_show(raw)


@lru_cache(maxsize=1)
def get_datapath_metrics_collector() -> DatapathMetricsCollector:
    return DatapathMetricsCollector(interval_s=get_settings().datapath_metrics_interval_s)

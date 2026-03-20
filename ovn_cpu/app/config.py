from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _split_csv(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    proc_root: str
    sample_interval_s: float
    history_size: int
    default_top_threads: int
    default_threads_per_component: int
    default_history_limit: int
    enable_kernel_threads: bool
    softirq_names: tuple[str, ...]
    user_process_names: tuple[str, ...]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        host=os.getenv("OVN_CPU_HOST", "0.0.0.0"),
        port=int(os.getenv("OVN_CPU_PORT", "8002")),
        proc_root=os.getenv("OVN_CPU_PROC_ROOT", "/proc"),
        sample_interval_s=max(float(os.getenv("OVN_CPU_SAMPLE_INTERVAL_S", "1.0")), 0.25),
        history_size=max(int(os.getenv("OVN_CPU_HISTORY_SIZE", "900")), 10),
        default_top_threads=max(int(os.getenv("OVN_CPU_TOP_THREADS", "20")), 1),
        default_threads_per_component=max(int(os.getenv("OVN_CPU_THREADS_PER_COMPONENT", "5")), 1),
        default_history_limit=max(int(os.getenv("OVN_CPU_HISTORY_LIMIT", "120")), 1),
        enable_kernel_threads=os.getenv("OVN_CPU_ENABLE_KERNEL_THREADS", "true").lower()
        in {"1", "true", "yes", "on"},
        softirq_names=_split_csv(os.getenv("OVN_CPU_SOFTIRQS", "NET_RX,NET_TX,RCU,TIMER,SCHED,HRTIMER")),
        user_process_names=_split_csv(
            os.getenv(
                "OVN_CPU_PROCESS_NAMES",
                "ovs-vswitchd,ovsdb-server,ovn-controller,ovn-controller-vtep,ovn-northd",
            )
        ),
    )

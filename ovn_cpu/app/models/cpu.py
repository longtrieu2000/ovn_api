from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CpuUsage(BaseModel):
    total_pct: float = Field(..., description="Total CPU usage percent across the last sample window.")
    user_pct: float = Field(..., description="User CPU usage percent across the last sample window.")
    system_pct: float = Field(..., description="System CPU usage percent across the last sample window.")


class SoftirqDelta(BaseModel):
    name: str
    total_delta: int
    per_cpu_delta: list[int]


class ThreadCpuSample(BaseModel):
    pid: int
    tid: int
    process_name: str
    process_component: str
    process_category: str
    process_label: str
    thread_name: str
    thread_group: str
    state: str
    wchan: str | None = None
    cpu: CpuUsage


class ThreadGroupSample(BaseModel):
    component: str
    category: str
    thread_group: str
    threads: int
    cpu: CpuUsage


class ProcessCpuSample(BaseModel):
    pid: int
    process_name: str
    component: str
    category: str
    label: str
    cmdline: str
    thread_count: int
    cpu: CpuUsage
    hot_threads: list[ThreadCpuSample]


class CpuSnapshot(BaseModel):
    generated_at: datetime
    elapsed_s: float
    warmup: bool
    cpu_count: int
    host_cpu_pct: float | None = None
    loadavg: list[float]
    components: list[ProcessCpuSample]
    top_threads: list[ThreadCpuSample]
    thread_groups: list[ThreadGroupSample]
    softirqs: list[SoftirqDelta]


class CpuHistoryPoint(BaseModel):
    generated_at: datetime
    elapsed_s: float
    warmup: bool
    host_cpu_pct: float | None = None
    components: list[ProcessCpuSample]
    top_threads: list[ThreadCpuSample]
    softirqs: list[SoftirqDelta]


class CpuSpike(BaseModel):
    generated_at: datetime
    component: str
    pid: int
    cpu: CpuUsage
    hot_threads: list[ThreadCpuSample]

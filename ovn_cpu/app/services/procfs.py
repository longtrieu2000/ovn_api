from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CpuStat:
    user: int
    nice: int
    system: int
    idle: int
    iowait: int
    irq: int
    softirq: int
    steal: int
    guest: int = 0
    guest_nice: int = 0

    @property
    def total(self) -> int:
        return (
            self.user
            + self.nice
            + self.system
            + self.idle
            + self.iowait
            + self.irq
            + self.softirq
            + self.steal
            + self.guest
            + self.guest_nice
        )

    @property
    def busy(self) -> int:
        return self.total - self.idle - self.iowait


@dataclass(frozen=True)
class SchedEntityStat:
    pid: int
    comm: str
    state: str
    ppid: int
    utime: int
    stime: int
    num_threads: int
    starttime: int


def parse_stat_line(raw: str) -> SchedEntityStat:
    left = raw.find("(")
    right = raw.rfind(")")
    if left == -1 or right == -1 or right <= left:
        raise ValueError(f"Malformed stat line: {raw!r}")

    pid = int(raw[:left].strip())
    comm = raw[left + 1 : right]
    fields = raw[right + 1 :].strip().split()
    if len(fields) < 20:
        raise ValueError(f"Malformed stat payload: {raw!r}")

    return SchedEntityStat(
        pid=pid,
        comm=comm,
        state=fields[0],
        ppid=int(fields[1]),
        utime=int(fields[11]),
        stime=int(fields[12]),
        num_threads=int(fields[17]),
        starttime=int(fields[19]),
    )


class ProcfsReader:
    def __init__(self, proc_root: str) -> None:
        self.root = Path(proc_root)

    def list_pids(self) -> list[int]:
        pids: list[int] = []
        for entry in self.root.iterdir():
            if entry.is_dir() and entry.name.isdigit():
                pids.append(int(entry.name))
        return pids

    def list_task_ids(self, pid: int) -> list[int]:
        task_dir = self.root / str(pid) / "task"
        tids: list[int] = []
        for entry in task_dir.iterdir():
            if entry.is_dir() and entry.name.isdigit():
                tids.append(int(entry.name))
        return tids

    def read_process_stat(self, pid: int) -> SchedEntityStat:
        return parse_stat_line(self._read_text(self.root / str(pid) / "stat"))

    def read_task_stat(self, pid: int, tid: int) -> SchedEntityStat:
        return parse_stat_line(self._read_text(self.root / str(pid) / "task" / str(tid) / "stat"))

    def read_cmdline(self, pid: int) -> str:
        raw = self._read_bytes(self.root / str(pid) / "cmdline")
        return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()

    def read_wchan(self, pid: int, tid: int | None = None) -> str | None:
        path = self.root / str(pid) / "wchan"
        if tid is not None:
            path = self.root / str(pid) / "task" / str(tid) / "wchan"
        try:
            value = self._read_text(path).strip()
        except OSError:
            return None
        return value or None

    def read_system_cpu(self) -> CpuStat:
        with (self.root / "stat").open("r", encoding="utf-8") as fh:
            first_line = fh.readline().strip()

        parts = first_line.split()
        if not parts or parts[0] != "cpu":
            raise ValueError("Could not find aggregate CPU line in /proc/stat.")

        values = [int(value) for value in parts[1:]]
        while len(values) < 10:
            values.append(0)
        return CpuStat(*values[:10])

    def read_softirqs(self, names: tuple[str, ...]) -> dict[str, list[int]]:
        with (self.root / "softirqs").open("r", encoding="utf-8") as fh:
            lines = fh.readlines()

        wanted = set(names)
        result: dict[str, list[int]] = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            name, payload = line.split(":", 1)
            name = name.strip()
            if name not in wanted:
                continue
            result[name] = [int(part) for part in payload.split()]

        for name in names:
            result.setdefault(name, [])
        return result

    def read_loadavg(self) -> tuple[float, float, float]:
        try:
            with (self.root / "loadavg").open("r", encoding="utf-8") as fh:
                fields = fh.read().strip().split()
            return float(fields[0]), float(fields[1]), float(fields[2])
        except (OSError, ValueError, IndexError):
            return os.getloadavg()

    def _read_text(self, path: Path) -> str:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read()

    def _read_bytes(self, path: Path) -> bytes:
        with path.open("rb") as fh:
            return fh.read()

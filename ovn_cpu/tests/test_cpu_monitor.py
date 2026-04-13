from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from ovn_cpu.app.config import Settings
from ovn_cpu.app.services.cpu_monitor import CpuMonitorService
from ovn_cpu.app.services.procfs import parse_stat_line


def make_stat(pid: int, comm: str, *, ppid: int, utime: int, stime: int, num_threads: int, starttime: int) -> str:
    fields = [
        "S",
        str(ppid),
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        str(utime),
        str(stime),
        "0",
        "0",
        "20",
        "0",
        str(num_threads),
        "0",
        str(starttime),
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
    ]
    return f"{pid} ({comm}) " + " ".join(fields)


class CpuMonitorTests(unittest.TestCase):
    def test_parse_stat_line(self) -> None:
        stat = parse_stat_line(make_stat(123, "ovs-vswitchd", ppid=1, utime=10, stime=5, num_threads=4, starttime=999))
        self.assertEqual(stat.pid, 123)
        self.assertEqual(stat.comm, "ovs-vswitchd")
        self.assertEqual(stat.ppid, 1)
        self.assertEqual(stat.utime, 10)
        self.assertEqual(stat.stime, 5)
        self.assertEqual(stat.num_threads, 4)
        self.assertEqual(stat.starttime, 999)

    def test_collect_snapshot_from_fake_proc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_file(root / "stat", "cpu  100 0 100 1000 0 0 0 0 0 0\n")
            self._write_file(root / "loadavg", "0.50 0.25 0.10 1/100 999\n")
            self._write_file(
                root / "softirqs",
                "                    CPU0       CPU1\n"
                "NET_RX:               10         20\n"
                "NET_TX:                5          5\n"
                "RCU:                   0          0\n"
                "TIMER:                 0          0\n"
                "SCHED:                 0          0\n"
                "HRTIMER:               0          0\n",
            )

            self._write_process(
                root,
                pid=100,
                comm="ovs-vswitchd",
                cmdline=b"ovs-vswitchd\x00unix:/var/run/openvswitch/db.sock\x00",
                proc_utime=100,
                proc_stime=50,
                proc_threads=3,
                proc_start=1000,
                tasks=[
                    (100, "ovs-vswitchd", 60, 30, 1000),
                    (101, "handler", 20, 10, 1001),
                    (102, "revalidator", 20, 10, 1002),
                ],
            )
            self._write_process(
                root,
                pid=200,
                comm="ovsdb-server",
                cmdline=b"ovsdb-server\x00/var/lib/ovn/ovnsb_db.db\x00",
                proc_utime=40,
                proc_stime=10,
                proc_threads=1,
                proc_start=2000,
                tasks=[(200, "ovsdb-server", 40, 10, 2000)],
            )

            settings = Settings(
                host="0.0.0.0",
                port=8002,
                proc_root=str(root),
                sample_interval_s=1.0,
                history_size=10,
                default_top_threads=10,
                default_threads_per_component=3,
                default_history_limit=10,
                enable_kernel_threads=True,
                softirq_names=("NET_RX", "NET_TX", "RCU", "TIMER", "SCHED", "HRTIMER"),
                user_process_names=("ovs-vswitchd", "ovsdb-server", "ovn-controller", "ovn-controller-vtep", "ovn-northd"),
            )

            service = CpuMonitorService(settings=settings)
            service.collect_now()
            time.sleep(0.05)

            self._write_file(root / "stat", "cpu  120 0 130 1050 0 0 0 0 0 0\n")
            self._write_file(
                root / "softirqs",
                "                    CPU0       CPU1\n"
                "NET_RX:               15         30\n"
                "NET_TX:               10          8\n"
                "RCU:                   0          0\n"
                "TIMER:                 0          0\n"
                "SCHED:                 0          0\n"
                "HRTIMER:               0          0\n",
            )
            self._write_process(
                root,
                pid=100,
                comm="ovs-vswitchd",
                cmdline=b"ovs-vswitchd\x00unix:/var/run/openvswitch/db.sock\x00",
                proc_utime=130,
                proc_stime=70,
                proc_threads=3,
                proc_start=1000,
                tasks=[
                    (100, "ovs-vswitchd", 75, 40, 1000),
                    (101, "handler", 28, 16, 1001),
                    (102, "revalidator", 27, 14, 1002),
                ],
            )
            self._write_process(
                root,
                pid=200,
                comm="ovsdb-server",
                cmdline=b"ovsdb-server\x00/var/lib/ovn/ovnsb_db.db\x00",
                proc_utime=55,
                proc_stime=15,
                proc_threads=1,
                proc_start=2000,
                tasks=[(200, "ovsdb-server", 55, 15, 2000)],
            )

            service.collect_now()
            snapshot = service.get_snapshot(threads_per_component=3, top_threads=10)
            payload = service.render_prometheus_text()

            components = {component.component: component for component in snapshot.components}
            self.assertIn("ovs-vswitchd", components)
            self.assertIn("ovn-sb-db", components)
            self.assertGreater(snapshot.host_cpu_pct or 0.0, 0.0)

            vswitchd = components["ovs-vswitchd"]
            self.assertEqual(vswitchd.hot_threads[0].thread_group, "main")
            self.assertIn("handler", {thread.thread_group for thread in vswitchd.hot_threads})
            self.assertIn("revalidator", {thread.thread_group for thread in vswitchd.hot_threads})

            sb_db = components["ovn-sb-db"]
            self.assertGreater(sb_db.cpu.total_pct, 0.0)

            handler_threads = service.get_threads(
                component="ovs-vswitchd",
                thread_group="handler",
                limit=5,
                min_cpu_pct=0.0,
            )
            self.assertEqual(len(handler_threads), 1)
            self.assertEqual(handler_threads[0].thread_name, "handler")

            spikes = service.find_spikes(component="ovn-sb-db", threshold_pct=0.1, limit=5)
            self.assertEqual(len(spikes), 1)
            self.assertEqual(spikes[0].component, "ovn-sb-db")

            self.assertIn("ovn_cpu_component_cpu_percent", payload)
            self.assertIn('component="ovn-sb-db"', payload)
            self.assertIn('thread_group="handler"', payload)
            self.assertIn('name="NET_RX"', payload)

    def _write_process(
        self,
        root: Path,
        *,
        pid: int,
        comm: str,
        cmdline: bytes,
        proc_utime: int,
        proc_stime: int,
        proc_threads: int,
        proc_start: int,
        tasks: list[tuple[int, str, int, int, int]],
    ) -> None:
        self._write_file(
            root / str(pid) / "stat",
            make_stat(
                pid,
                comm,
                ppid=1,
                utime=proc_utime,
                stime=proc_stime,
                num_threads=proc_threads,
                starttime=proc_start,
            ),
        )
        self._write_bytes(root / str(pid) / "cmdline", cmdline)
        for tid, task_comm, utime, stime, starttime in tasks:
            self._write_file(
                root / str(pid) / "task" / str(tid) / "stat",
                make_stat(
                    tid,
                    task_comm,
                    ppid=pid,
                    utime=utime,
                    stime=stime,
                    num_threads=1,
                    starttime=starttime,
                ),
            )

    def _write_file(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _write_bytes(self, path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


if __name__ == "__main__":
    unittest.main()

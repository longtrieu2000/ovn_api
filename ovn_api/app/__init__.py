from __future__ import annotations

import os
import sys
import types
from pathlib import Path


def _bootstrap_local_ovs_python_path() -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    ovs_python_path = workspace_root / "ovs" / "python"
    if not ovs_python_path.exists():
        return

    resolved = str(ovs_python_path)
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


def _bootstrap_local_ovs_dirs_module() -> None:
    try:
        import ovs.dirs  # noqa: F401
        return
    except ModuleNotFoundError as exc:
        if exc.name != "ovs.dirs":
            raise

    workspace_root = Path(__file__).resolve().parents[2]
    workspace_ovs_root = workspace_root / "ovs"

    module = types.ModuleType("ovs.dirs")
    module.PKGDATADIR = os.environ.get(
        "OVS_PKGDATADIR",
        str(workspace_ovs_root / "vswitchd"),
    )
    module.RUNDIR = os.environ.get("OVS_RUNDIR", "/var/run/openvswitch")
    module.LOGDIR = os.environ.get("OVS_LOGDIR", "/var/log/openvswitch")
    module.BINDIR = os.environ.get("OVS_BINDIR", "/usr/bin")
    module.DBDIR = os.environ.get("OVS_DBDIR") or (
        f"{os.environ.get('OVS_SYSCONFDIR', '/etc')}/openvswitch"
    )
    sys.modules["ovs.dirs"] = module

    ovs_pkg = sys.modules.get("ovs")
    if ovs_pkg is not None:
        setattr(ovs_pkg, "dirs", module)


_bootstrap_local_ovs_python_path()
_bootstrap_local_ovs_dirs_module()

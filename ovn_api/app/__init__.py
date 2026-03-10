from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_local_ovs_python_path() -> None:
    workspace_root = Path(__file__).resolve().parents[2]
    ovs_python_path = workspace_root / "ovs" / "python"
    if not ovs_python_path.exists():
        return

    resolved = str(ovs_python_path)
    if resolved not in sys.path:
        sys.path.insert(0, resolved)


_bootstrap_local_ovs_python_path()

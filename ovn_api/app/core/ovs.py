from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .command import CommandExecutor


class OvsCommandClient:
    def __init__(
        self,
        *,
        ovs_ofctl_bin: str,
        ovs_vswitchd_container: str,
        executor: CommandExecutor,
    ) -> None:
        self.ovs_ofctl_bin = ovs_ofctl_bin
        self.ovs_vswitchd_container = ovs_vswitchd_container
        self.executor = executor

    def dump_openflow_flows(self, bridge: str) -> str:
        result = self.executor.run(
            [self.ovs_ofctl_bin, "dump-flows", bridge],
            container=self.ovs_vswitchd_container,
        )
        return result.stdout


@lru_cache(maxsize=1)
def get_ovs_command_client() -> OvsCommandClient:
    settings = get_settings()
    return OvsCommandClient(
        ovs_ofctl_bin=settings.ovs_ofctl_bin,
        ovs_vswitchd_container=settings.ovs_vswitchd_container,
        executor=CommandExecutor(
            transport=settings.command_transport,
            docker_bin=settings.docker_bin,
        ),
    )

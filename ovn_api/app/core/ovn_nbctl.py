from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from .command import CommandExecutor


class OvnNbCommandClient:
    def __init__(
        self,
        *,
        ovn_nbctl_bin: str,
        ovn_nb_container: str,
        executor: CommandExecutor,
    ) -> None:
        self.ovn_nbctl_bin = ovn_nbctl_bin
        self.ovn_nb_container = ovn_nb_container
        self.executor = executor

    def run(self, args: list[str]) -> str:
        result = self.executor.run(
            [self.ovn_nbctl_bin, *args],
            container=self.ovn_nb_container,
        )
        return result.stdout


@lru_cache(maxsize=1)
def get_ovn_nb_command_client() -> OvnNbCommandClient:
    settings = get_settings()
    return OvnNbCommandClient(
        ovn_nbctl_bin=settings.ovn_nbctl_bin,
        ovn_nb_container=settings.ovn_nb_container,
        executor=CommandExecutor(
            transport=settings.command_transport,
            docker_bin=settings.docker_bin,
        ),
    )

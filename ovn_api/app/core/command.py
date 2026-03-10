from __future__ import annotations

import subprocess

from fastapi import HTTPException


class CommandExecutor:
    def __init__(self, *, transport: str, docker_bin: str) -> None:
        self.transport = transport
        self.docker_bin = docker_bin

    def run(self, args: list[str], *, container: str | None = None) -> subprocess.CompletedProcess[str]:
        command = self._build_command(args=args, container=container)
        try:
            return subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            missing_bin = command[0] if command else "command"
            raise HTTPException(
                status_code=500,
                detail=f"{missing_bin!r} not found on PATH.",
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else str(exc)
            raise HTTPException(
                status_code=500,
                detail=f"Command failed: {' '.join(command)}: {stderr}",
            ) from exc

    def _build_command(self, *, args: list[str], container: str | None) -> list[str]:
        if self.transport == "local":
            return args

        if self.transport == "docker-exec":
            if not container:
                raise HTTPException(
                    status_code=500,
                    detail="Container name is required when OVN_COMMAND_TRANSPORT=docker-exec.",
                )
            return [self.docker_bin, "exec", container, *args]

        raise HTTPException(
            status_code=500,
            detail=(
                "Unsupported OVN_COMMAND_TRANSPORT. "
                f"Expected 'local' or 'docker-exec', got {self.transport!r}."
            ),
        )

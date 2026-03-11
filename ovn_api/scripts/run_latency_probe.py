#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


def _fetch_json(url: str, timeout_s: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def _snapshot(api_base: str, timeout_s: float) -> dict:
    return {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "latency": _fetch_json(f"{api_base}/api/v1/metrics/latency", timeout_s),
        "capacity": _fetch_json(f"{api_base}/api/v1/metrics/capacity", timeout_s),
        "flow_summary": _fetch_json(f"{api_base}/api/v1/flows/logical/summary", timeout_s),
    }


def _print_snapshot(label: str, snapshot: dict) -> None:
    latency = snapshot["latency"]
    ovsdb = latency["ovsdb"]
    bfd = latency["bfd"]
    flow_summary = snapshot["flow_summary"]
    capacity = snapshot["capacity"]

    print(f"\n[{label}] {snapshot['captured_at']}")
    print(
        "  ovsdb: "
        f"nb_tx={ovsdb['nb_transaction_latency_ms']}ms "
        f"sb_tx={ovsdb['sb_transaction_latency_ms']}ms "
        f"nb_idl={ovsdb['nb_idl_sync_latency_ms']}ms "
        f"sb_idl={ovsdb['sb_idl_sync_latency_ms']}ms"
    )
    print(
        "  bfd: "
        f"sessions={bfd['session_count']} "
        f"up={bfd['up_count']} "
        f"down={bfd['down_count']} "
        f"admin_down={bfd['admin_down_count']} "
        f"init={bfd['init_count']}"
    )
    print(
        "  flows: "
        f"total={flow_summary['logical_flow_count']} "
        f"acl={flow_summary['acl_logical_flow_count']} "
        f"acl_exact={flow_summary['acl_exact_logical_flow_count']} "
        f"acl_stage={flow_summary['acl_stage_generic_logical_flow_count']} "
        f"nat={flow_summary['nat_logical_flow_count']} "
        f"nat_exact={flow_summary['nat_exact_logical_flow_count']} "
        f"nat_stage={flow_summary['nat_stage_generic_logical_flow_count']} "
        f"other={flow_summary['other_logical_flow_count']}"
    )
    print(
        "  capacity: "
        f"switches={capacity['logical_switch_count']} "
        f"routers={capacity['logical_router_count']} "
        f"acls={capacity['acl_count']} "
        f"logical_flows={capacity['logical_flow_count']}"
    )

    openflow = latency["openflow_installation"]
    if not openflow["available"]:
        print(f"  openflow_installation: {openflow['measurement_mode']} ({openflow['reason']})")


def _run_ovn_nbctl(
    docker_bin: str,
    container: str,
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = [docker_bin, "exec", container, "ovn-nbctl", *args]
    return subprocess.run(command, check=check, capture_output=True, text=True)


def _probe_step(
    step_name: str,
    action_args: list[str],
    *,
    api_base: str,
    timeout_s: float,
    docker_bin: str,
    nb_container: str,
    sample_count: int,
    sample_interval_s: float,
    results: list[dict],
) -> None:
    started_at = time.perf_counter()
    result = _run_ovn_nbctl(docker_bin, nb_container, action_args)
    action_latency_ms = round((time.perf_counter() - started_at) * 1000, 3)

    step_record = {
        "step": step_name,
        "action_args": action_args,
        "command_latency_ms": action_latency_ms,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "samples": [],
    }
    print(f"\n== {step_name} ==")
    print(f"ovn-nbctl latency: {action_latency_ms}ms")

    for sample_index in range(1, sample_count + 1):
        snapshot = _snapshot(api_base, timeout_s)
        sample_label = f"{step_name} sample {sample_index}/{sample_count}"
        _print_snapshot(sample_label, snapshot)
        step_record["samples"].append(snapshot)
        if sample_index < sample_count:
            time.sleep(sample_interval_s)

    results.append(step_record)


def _best_effort_cleanup(docker_bin: str, nb_container: str, cleanup_steps: list[tuple[str, list[str]]]) -> None:
    for _, args in cleanup_steps:
        try:
            _run_ovn_nbctl(docker_bin, nb_container, args, check=False)
        except Exception:
            continue


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create/delete OVN NB resources and capture API latency metrics after each step.",
    )
    parser.add_argument("--api-base", default="http://127.0.0.1:8001", help="Base URL of the OVN API service.")
    parser.add_argument("--docker-bin", default="docker", help="Docker CLI binary.")
    parser.add_argument("--nb-container", default="ovn_nb_db", help="Container running ovn-nbctl.")
    parser.add_argument(
        "--prefix",
        default=f"latprobe-{int(time.time())}",
        help="Unique resource prefix used for the temporary OVN objects.",
    )
    parser.add_argument("--sample-count", type=int, default=3, help="How many API samples to capture after each step.")
    parser.add_argument(
        "--sample-interval",
        type=float,
        default=2.0,
        help="Seconds between samples after each create/delete step.",
    )
    parser.add_argument("--http-timeout", type=float, default=5.0, help="HTTP timeout for API requests.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON file path to write the full probe result.",
    )
    args = parser.parse_args()

    logical_switch = f"{args.prefix}-ls"
    logical_router = f"{args.prefix}-lr"
    router_port = f"{args.prefix}-lrp"
    switch_port = f"{args.prefix}-lsp"

    steps = [
        ("create_logical_switch", ["ls-add", logical_switch]),
        ("create_logical_router", ["lr-add", logical_router]),
        ("create_router_port", ["lrp-add", logical_router, router_port, "aa:bb:cc:dd:ee:01", "10.254.0.1/24"]),
        ("create_switch_router_port", ["lsp-add", logical_switch, switch_port]),
        ("set_switch_port_type_router", ["lsp-set-type", switch_port, "router"]),
        ("set_switch_port_addresses_router", ["lsp-set-addresses", switch_port, "router"]),
        ("set_switch_port_option_router_port", ["lsp-set-options", switch_port, f"router-port={router_port}"]),
        ("add_acl_drop_ip4", ["acl-add", logical_switch, "to-lport", "1001", "ip4", "drop"]),
        ("delete_acl_drop_ip4", ["acl-del", logical_switch, "to-lport", "1001", "ip4"]),
        ("delete_switch_port", ["lsp-del", switch_port]),
        ("delete_router_port", ["lrp-del", router_port]),
        ("delete_logical_router", ["lr-del", logical_router]),
        ("delete_logical_switch", ["ls-del", logical_switch]),
    ]

    cleanup_steps = [
        ("cleanup_acl_drop_ip4", ["acl-del", logical_switch, "to-lport", "1001", "ip4"]),
        ("cleanup_switch_port", ["lsp-del", switch_port]),
        ("cleanup_router_port", ["lrp-del", router_port]),
        ("cleanup_logical_router", ["lr-del", logical_router]),
        ("cleanup_logical_switch", ["ls-del", logical_switch]),
    ]

    results: list[dict] = []
    run_record = {
        "api_base": args.api_base,
        "nb_container": args.nb_container,
        "prefix": args.prefix,
        "sample_count": args.sample_count,
        "sample_interval": args.sample_interval,
        "steps": results,
    }

    try:
        baseline = _snapshot(args.api_base, args.http_timeout)
        run_record["baseline"] = baseline
        _print_snapshot("baseline", baseline)

        for step_name, action_args in steps:
            _probe_step(
                step_name,
                action_args,
                api_base=args.api_base,
                timeout_s=args.http_timeout,
                docker_bin=args.docker_bin,
                nb_container=args.nb_container,
                sample_count=args.sample_count,
                sample_interval_s=args.sample_interval,
                results=results,
            )
    except urllib.error.URLError as exc:
        print(f"Failed to reach API at {args.api_base}: {exc}", file=sys.stderr)
        _best_effort_cleanup(args.docker_bin, args.nb_container, cleanup_steps)
        return 1
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else str(exc)
        print(f"ovn-nbctl command failed: {' '.join(exc.cmd)}: {stderr}", file=sys.stderr)
        _best_effort_cleanup(args.docker_bin, args.nb_container, cleanup_steps)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted. Running cleanup.", file=sys.stderr)
        _best_effort_cleanup(args.docker_bin, args.nb_container, cleanup_steps)
        return 130

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(run_record, indent=2), encoding="utf-8")
        print(f"\nWrote probe result to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

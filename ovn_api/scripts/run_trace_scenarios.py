#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


FINAL_STATUSES = {"success", "partial_success", "timeout", "failed"}


@dataclass(frozen=True)
class Scenario:
    name: str
    resource_type: str
    target_name: str | None = None
    expect_openflow: bool | None = None


def _http_json(
    method: str,
    url: str,
    timeout_s: float,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, method=method, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def _metrics_snapshot(api_base: str, timeout_s: float) -> dict[str, Any]:
    latency = _http_json("GET", f"{api_base}/api/v1/metrics/latency", timeout_s)
    capacity = _http_json("GET", f"{api_base}/api/v1/metrics/capacity", timeout_s)
    flow_summary = _http_json("GET", f"{api_base}/api/v1/flows/logical/summary", timeout_s)
    if not isinstance(latency, dict) or not isinstance(capacity, dict) or not isinstance(flow_summary, dict):
        raise RuntimeError("Unexpected metrics snapshot response.")
    return {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "latency": latency,
        "capacity": capacity,
        "flow_summary": flow_summary,
    }


def _submit_sync_probe(api_base: str, timeout_s: float, payload: dict[str, Any]) -> dict[str, Any]:
    response = _http_json("POST", f"{api_base}/api/v1/traces/canary", timeout_s, payload)
    if not isinstance(response, dict):
        raise RuntimeError("Unexpected sync trace response.")
    return response


def _submit_async_probe(api_base: str, timeout_s: float, payload: dict[str, Any]) -> dict[str, Any]:
    response = _http_json("POST", f"{api_base}/api/v1/traces/canary/runs", timeout_s, payload)
    if not isinstance(response, dict):
        raise RuntimeError("Unexpected async trace response.")
    return response


def _get_run(api_base: str, timeout_s: float, probe_id: str) -> dict[str, Any]:
    response = _http_json("GET", f"{api_base}/api/v1/traces/canary/runs/{probe_id}", timeout_s)
    if not isinstance(response, dict):
        raise RuntimeError("Unexpected run detail response.")
    return response


def _poll_run(
    api_base: str,
    timeout_s: float,
    probe_id: str,
    *,
    wait_timeout_s: float,
    poll_interval_s: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + wait_timeout_s
    while time.monotonic() <= deadline:
        detail = _get_run(api_base, timeout_s, probe_id)
        status = detail.get("status")
        print(
            "  poll: "
            f"probe_id={probe_id} status={status} "
            f"started_at={detail.get('started_at')} finished_at={detail.get('finished_at')}"
        )
        if status in FINAL_STATUSES:
            return detail
        time.sleep(poll_interval_s)
    raise TimeoutError(f"Timed out waiting for async probe {probe_id} after {wait_timeout_s}s.")


def _build_payload(
    scenario: Scenario,
    *,
    bridge: str,
    trace_timeout_s: float,
    trace_poll_interval_ms: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "resource_type": scenario.resource_type,
        "bridge": bridge,
        "timeout_s": trace_timeout_s,
        "poll_interval_ms": trace_poll_interval_ms,
    }
    if scenario.target_name is not None:
        payload["target_name"] = scenario.target_name
    if scenario.expect_openflow is not None:
        payload["expect_openflow"] = scenario.expect_openflow
    return payload


def _extract_result_payload(run_or_result: dict[str, Any]) -> dict[str, Any]:
    nested = run_or_result.get("result")
    if isinstance(nested, dict):
        return nested
    return run_or_result


def _print_snapshot(label: str, snapshot: dict[str, Any]) -> None:
    latency = snapshot["latency"]
    ovsdb = latency["ovsdb"]
    bfd = latency["bfd"]
    capacity = snapshot["capacity"]
    flow_summary = snapshot["flow_summary"]
    print(f"\n[{label}] captured_at={snapshot['captured_at']}")
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
        "  capacity: "
        f"switches={capacity['logical_switch_count']} "
        f"routers={capacity['logical_router_count']} "
        f"ports={capacity['logical_switch_port_count']} "
        f"logical_flows={capacity['logical_flow_count']} "
        f"acls={capacity['acl_count']}"
    )
    print(
        "  flows: "
        f"total={flow_summary['logical_flow_count']} "
        f"acl={flow_summary['acl_logical_flow_count']} "
        f"nat={flow_summary['nat_logical_flow_count']} "
        f"other={flow_summary['other_logical_flow_count']}"
    )


def _print_trace_result(label: str, result: dict[str, Any]) -> None:
    print(f"\n[{label}]")
    print(
        "  trace: "
        f"probe_id={result['probe_id']} "
        f"status={result['status']} "
        f"resource={result['requested_resource_type']}->{result['resolved_resource_type']} "
        f"resource_name={result['resource_name']}"
    )
    print(
        "  latency: "
        f"command={result['command_latency_ms']}ms "
        f"nb_to_sb={result.get('nb_to_sb_latency_ms')}ms "
        f"sb_to_openflow={result.get('sb_to_openflow_latency_ms')}ms "
        f"total={result.get('total_latency_ms')}ms"
    )
    print(
        "  stages: "
        f"nb={result['nb_committed']['status']} "
        f"sb={result['sb_realized']['status']} "
        f"of={result['openflow_realized']['status']} "
        f"cleanup={result['cleanup']['status']}"
    )
    if result.get("note"):
        print(f"  note: {result['note']}")


def _run_scenario(
    api_base: str,
    scenario: Scenario,
    *,
    mode: str,
    bridge: str,
    http_timeout_s: float,
    trace_timeout_s: float,
    trace_poll_interval_ms: int,
    wait_timeout_s: float,
    wait_interval_s: float,
) -> dict[str, Any]:
    payload = _build_payload(
        scenario,
        bridge=bridge,
        trace_timeout_s=trace_timeout_s,
        trace_poll_interval_ms=trace_poll_interval_ms,
    )
    before_snapshot = _metrics_snapshot(api_base, http_timeout_s)

    started_at = time.perf_counter()
    if mode == "sync":
        run_response = _submit_sync_probe(api_base, http_timeout_s, payload)
    else:
        submitted = _submit_async_probe(api_base, http_timeout_s, payload)
        run_response = _poll_run(
            api_base,
            http_timeout_s,
            submitted["probe_id"],
            wait_timeout_s=wait_timeout_s,
            poll_interval_s=wait_interval_s,
        )
    scenario_elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)

    result_payload = _extract_result_payload(run_response)
    after_snapshot = _metrics_snapshot(api_base, http_timeout_s)

    return {
        "scenario": asdict(scenario),
        "payload": payload,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_ms": scenario_elapsed_ms,
        "metrics_before": before_snapshot,
        "trace_response": run_response,
        "trace_result": result_payload,
        "metrics_after": after_snapshot,
    }


def _default_scenarios(
    *,
    switch_target: str | None,
    router_target: str | None,
    enable_openflow: bool,
) -> list[Scenario]:
    switch_expect_openflow = True if switch_target and enable_openflow else None
    return [
        Scenario(name="create_delete_logical_router", resource_type="logical_router", target_name=router_target),
        Scenario(name="create_delete_logical_switch", resource_type="logical_switch", target_name=switch_target),
        Scenario(
            name="create_delete_acl",
            resource_type="acl",
            target_name=switch_target,
            expect_openflow=switch_expect_openflow,
        ),
        Scenario(
            name="create_delete_logical_flow",
            resource_type="logical_flow",
            target_name=switch_target,
            expect_openflow=switch_expect_openflow,
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a matrix of OVN canary scenarios for logical_router, logical_switch, ACL, and logical_flow, "
            "capturing trace latency plus metrics snapshots before/after each scenario."
        )
    )
    parser.add_argument("--api-base", default="http://127.0.0.1:8001", help="Base URL of the OVN API service.")
    parser.add_argument("--mode", choices=("sync", "async"), default="async", help="Trace execution mode.")
    parser.add_argument("--bridge", default="br-int", help="Bridge passed to the canary trace API.")
    parser.add_argument("--switch-target", default=None, help="Existing logical switch for ACL/logical_flow openflow tests.")
    parser.add_argument("--router-target", default=None, help="Existing logical router if you want to reuse one.")
    parser.add_argument("--trace-timeout", type=float, default=15.0, help="Per-probe timeout sent to the API.")
    parser.add_argument(
        "--trace-poll-interval-ms",
        type=int,
        default=250,
        help="Per-probe polling interval sent to the API.",
    )
    parser.add_argument("--http-timeout", type=float, default=10.0, help="Timeout for each API request.")
    parser.add_argument("--wait-timeout", type=float, default=90.0, help="Async wait timeout per scenario.")
    parser.add_argument("--wait-interval", type=float, default=1.0, help="Async poll interval.")
    parser.add_argument(
        "--disable-openflow",
        action="store_true",
        help="Do not request openflow even if --switch-target is provided.",
    )
    parser.add_argument(
        "--sleep-between",
        type=float,
        default=1.5,
        help="Seconds to wait between scenarios so metrics snapshots are easier to compare.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON report path.")
    args = parser.parse_args()

    scenarios = _default_scenarios(
        switch_target=args.switch_target,
        router_target=args.router_target,
        enable_openflow=not args.disable_openflow,
    )

    report: dict[str, Any] = {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "api_base": args.api_base,
        "mode": args.mode,
        "bridge": args.bridge,
        "switch_target": args.switch_target,
        "router_target": args.router_target,
        "scenarios": [],
    }

    print("Scenario order:")
    for item in scenarios:
        print(f"  - {item.name}: resource_type={item.resource_type} target_name={item.target_name}")

    try:
        for index, scenario in enumerate(scenarios, start=1):
            print(f"\n=== Scenario {index}/{len(scenarios)}: {scenario.name} ===")
            scenario_record = _run_scenario(
                args.api_base,
                scenario,
                mode=args.mode,
                bridge=args.bridge,
                http_timeout_s=args.http_timeout,
                trace_timeout_s=args.trace_timeout,
                trace_poll_interval_ms=args.trace_poll_interval_ms,
                wait_timeout_s=args.wait_timeout,
                wait_interval_s=args.wait_interval,
            )
            report["scenarios"].append(scenario_record)
            _print_snapshot(f"{scenario.name} before", scenario_record["metrics_before"])
            _print_trace_result(f"{scenario.name} trace", scenario_record["trace_result"])
            _print_snapshot(f"{scenario.name} after", scenario_record["metrics_after"])
            if index < len(scenarios):
                time.sleep(args.sleep_between)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP error from API: {exc.code} {exc.reason}\n{body}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Failed to reach API at {args.api_base}: {exc}", file=sys.stderr)
        return 1
    except TimeoutError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Unexpected scenario runner error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("\nSummary")
    for scenario_record in report["scenarios"]:
        result = scenario_record["trace_result"]
        print(
            "  "
            f"{scenario_record['scenario']['name']}: "
            f"status={result['status']} "
            f"command={result['command_latency_ms']}ms "
            f"nb_to_sb={result.get('nb_to_sb_latency_ms')}ms "
            f"sb_to_openflow={result.get('sb_to_openflow_latency_ms')}ms "
            f"total={result.get('total_latency_ms')}ms"
        )

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote scenario report to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

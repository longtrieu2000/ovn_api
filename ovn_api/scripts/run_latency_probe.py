#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


FINAL_STATUSES = {"success", "partial_success", "timeout", "failed"}


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


def _fetch_capabilities(api_base: str, timeout_s: float) -> dict[str, Any]:
    response = _http_json("GET", f"{api_base}/api/v1/traces/capabilities", timeout_s)
    if not isinstance(response, dict):
        raise RuntimeError("Unexpected capabilities response.")
    return response


def _print_capabilities(capabilities: dict[str, Any]) -> None:
    print("\nCanary Trace Capabilities")
    print(f"  sync_endpoint: {capabilities['sync_endpoint']}")
    print(f"  async_submit_endpoint: {capabilities['async_submit_endpoint']}")
    print(f"  store_scope: {capabilities['store_scope']}")
    print("  resources:")
    for resource in capabilities.get("resources", []):
        stages = ",".join(resource.get("available_stages", []))
        openflow = "yes" if resource.get("openflow_supported") else "no"
        alias = resource.get("alias_for") or "-"
        print(
            "   - "
            f"{resource['requested_resource_type']}"
            f" -> {resource['resolved_resource_type']}"
            f" alias={alias}"
            f" openflow={openflow}"
            f" stages={stages}"
        )


def _print_stage(stage_name: str, stage: dict[str, Any]) -> None:
    evidence = stage.get("evidence") or []
    evidence_preview = evidence[0] if evidence else "-"
    print(
        f"  {stage_name}: "
        f"status={stage.get('status')} "
        f"latency_ms={stage.get('latency_ms')} "
        f"observed_at={stage.get('observed_at')} "
        f"detail={stage.get('detail')}"
    )
    print(f"    evidence: {evidence_preview}")


def _print_probe_result(result: dict[str, Any]) -> None:
    print("\nProbe Result")
    print(f"  probe_id: {result['probe_id']}")
    print(f"  status: {result['status']}")
    print(f"  resource: {result['requested_resource_type']} -> {result['resolved_resource_type']}")
    print(f"  resource_name: {result['resource_name']}")
    print(f"  target_name: {result.get('target_name')}")
    print(f"  openflow_expected: {result['openflow_expected']}")
    print(f"  command_latency_ms: {result['command_latency_ms']}")
    print(f"  nb_to_sb_latency_ms: {result.get('nb_to_sb_latency_ms')}")
    print(f"  sb_to_openflow_latency_ms: {result.get('sb_to_openflow_latency_ms')}")
    print(f"  total_latency_ms: {result.get('total_latency_ms')}")
    if result.get("note"):
        print(f"  note: {result['note']}")
    _print_stage("nb_committed", result["nb_committed"])
    _print_stage("sb_realized", result["sb_realized"])
    _print_stage("openflow_realized", result["openflow_realized"])
    _print_stage("cleanup", result["cleanup"])


def _submit_sync_probe(api_base: str, timeout_s: float, payload: dict[str, Any]) -> dict[str, Any]:
    response = _http_json("POST", f"{api_base}/api/v1/traces/canary", timeout_s, payload)
    if not isinstance(response, dict):
        raise RuntimeError("Unexpected sync probe response.")
    return response


def _submit_async_probe(api_base: str, timeout_s: float, payload: dict[str, Any]) -> dict[str, Any]:
    response = _http_json("POST", f"{api_base}/api/v1/traces/canary/runs", timeout_s, payload)
    if not isinstance(response, dict):
        raise RuntimeError("Unexpected async submit response.")
    return response


def _get_run(api_base: str, timeout_s: float, probe_id: str) -> dict[str, Any]:
    response = _http_json("GET", f"{api_base}/api/v1/traces/canary/runs/{probe_id}", timeout_s)
    if not isinstance(response, dict):
        raise RuntimeError("Unexpected run detail response.")
    return response


def _list_runs(api_base: str, timeout_s: float, limit: int) -> list[dict[str, Any]]:
    response = _http_json("GET", f"{api_base}/api/v1/traces/canary/runs?limit={limit}", timeout_s)
    if not isinstance(response, list):
        raise RuntimeError("Unexpected run list response.")
    return response


def _poll_async_run(
    api_base: str,
    timeout_s: float,
    probe_id: str,
    wait_timeout_s: float,
    poll_interval_s: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + wait_timeout_s
    while time.monotonic() <= deadline:
        detail = _get_run(api_base, timeout_s, probe_id)
        status = detail.get("status")
        print(
            f"  poll: probe_id={probe_id} status={status} "
            f"started_at={detail.get('started_at')} finished_at={detail.get('finished_at')}"
        )
        if status in FINAL_STATUSES:
            return detail
        time.sleep(poll_interval_s)
    raise TimeoutError(f"Timed out waiting for probe {probe_id} after {wait_timeout_s}s.")


def _build_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "resource_type": args.resource_type,
        "bridge": args.bridge,
        "timeout_s": args.trace_timeout,
        "poll_interval_ms": args.trace_poll_interval_ms,
    }
    if args.target_name is not None:
        payload["target_name"] = args.target_name
    if args.expect_openflow is not None:
        payload["expect_openflow"] = args.expect_openflow
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Test OVN canary trace APIs.")
    parser.add_argument("--api-base", default="http://127.0.0.1:8001", help="Base URL of the OVN API service.")
    parser.add_argument("--mode", choices=("sync", "async"), default="async", help="Trace execution mode.")
    parser.add_argument("--resource-type", default="acl", help="Canary resource_type to test.")
    parser.add_argument("--target-name", default=None, help="Existing OVN switch/router target for the canary.")
    parser.add_argument("--bridge", default="br-int", help="OpenFlow bridge for trace detection.")
    parser.add_argument("--trace-timeout", type=float, default=15.0, help="Probe timeout passed to the API.")
    parser.add_argument(
        "--trace-poll-interval-ms",
        type=int,
        default=250,
        help="Probe poll interval passed to the API.",
    )
    parser.add_argument(
        "--expect-openflow",
        dest="expect_openflow",
        action="store_true",
        default=None,
        help="Force expect_openflow=true in the probe request.",
    )
    parser.add_argument(
        "--no-expect-openflow",
        dest="expect_openflow",
        action="store_false",
        help="Force expect_openflow=false in the probe request.",
    )
    parser.add_argument("--http-timeout", type=float, default=10.0, help="HTTP timeout for each API call.")
    parser.add_argument("--wait-timeout", type=float, default=90.0, help="Async wait timeout.")
    parser.add_argument("--wait-interval", type=float, default=1.0, help="Async poll interval.")
    parser.add_argument("--show-capabilities", action="store_true", help="Print `/traces/capabilities` before running.")
    parser.add_argument("--list-runs", type=int, default=5, help="How many persisted runs to print at the end.")
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON file to write the collected output.")
    args = parser.parse_args()

    payload = _build_payload(args)
    run_record: dict[str, Any] = {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "api_base": args.api_base,
        "mode": args.mode,
        "payload": payload,
    }

    try:
        capabilities = _fetch_capabilities(args.api_base, args.http_timeout)
        run_record["capabilities"] = capabilities
        if args.show_capabilities:
            _print_capabilities(capabilities)

        if args.mode == "sync":
            result = _submit_sync_probe(args.api_base, args.http_timeout, payload)
            run_record["result"] = result
            _print_probe_result(result)
        else:
            submitted = _submit_async_probe(args.api_base, args.http_timeout, payload)
            run_record["submitted"] = submitted
            print(f"\nQueued async probe: probe_id={submitted['probe_id']} status={submitted['status']}")
            detail = _poll_async_run(
                args.api_base,
                args.http_timeout,
                submitted["probe_id"],
                args.wait_timeout,
                args.wait_interval,
            )
            run_record["result"] = detail
            if detail.get("result") is not None:
                _print_probe_result(detail["result"])
            else:
                print("\nProbe did not produce a result payload.")
                print(json.dumps(detail, indent=2))

        recent_runs = _list_runs(args.api_base, args.http_timeout, args.list_runs)
        run_record["recent_runs"] = recent_runs
        print(f"\nRecent persisted runs: {len(recent_runs)}")
        for item in recent_runs:
            print(
                "  "
                f"{item['probe_id']} status={item['status']} "
                f"resource={item['requested_resource_type']} "
                f"queued_at={item['queued_at']}"
            )
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
    except Exception as exc:
        print(f"Unexpected probe runner error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(run_record, indent=2), encoding="utf-8")
        print(f"\nWrote probe artifact to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

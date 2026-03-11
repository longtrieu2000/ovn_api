#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Any

from run_trace_scenarios import Scenario, _default_scenarios, _print_snapshot, _print_trace_result, _run_scenario


def _build_single_scenarios(args: argparse.Namespace) -> list[Scenario]:
    if args.resource_type is None:
        return _default_scenarios(
            switch_target=args.switch_target,
            router_target=args.router_target,
            enable_openflow=not args.disable_openflow,
        )

    return [
        Scenario(
            name=f"probe_{args.resource_type}",
            resource_type=args.resource_type,
            target_name=args.target_name,
            expect_openflow=args.expect_openflow,
        )
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Backward-compatible OVN latency probe runner. By default it runs a scenario matrix that creates/deletes "
            "logical_router, logical_switch, ACL, and logical_flow canaries, capturing metrics snapshots and trace "
            "latency around each scenario."
        )
    )
    parser.add_argument("--api-base", default="http://127.0.0.1:8001", help="Base URL of the OVN API service.")
    parser.add_argument(
        "--nb-container",
        default="ovn_nb_db",
        help="Backward-compatible option. Kept for CLI compatibility; the trace API now manages resources itself.",
    )
    parser.add_argument(
        "--sample-count",
        type=int,
        default=1,
        help="How many rounds to execute. Each round runs router, switch, ACL, and logical_flow scenarios.",
    )
    parser.add_argument(
        "--sample-interval",
        type=float,
        default=2.0,
        help="Seconds to wait between scenarios/rounds.",
    )
    parser.add_argument("--mode", choices=("sync", "async"), default="async", help="Trace execution mode.")
    parser.add_argument("--bridge", default="br-int", help="Bridge passed to the canary trace API.")
    parser.add_argument("--switch-target", default=None, help="Existing logical switch for ACL/logical_flow openflow tests.")
    parser.add_argument("--router-target", default=None, help="Existing logical router if you want to reuse one.")
    parser.add_argument(
        "--resource-type",
        default=None,
        help="Optional single resource_type. If omitted, the script runs the full matrix router/switch/ACL/logical_flow.",
    )
    parser.add_argument("--target-name", default=None, help="Optional target for single-resource mode.")
    parser.add_argument(
        "--expect-openflow",
        dest="expect_openflow",
        action="store_true",
        default=None,
        help="Force expect_openflow=true in single-resource mode.",
    )
    parser.add_argument(
        "--no-expect-openflow",
        dest="expect_openflow",
        action="store_false",
        help="Force expect_openflow=false in single-resource mode.",
    )
    parser.add_argument("--disable-openflow", action="store_true", help="Disable openflow for matrix mode even if targets exist.")
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
    parser.add_argument("--output", type=Path, default=None, help="Optional JSON report path.")
    args = parser.parse_args()

    if args.sample_count < 1:
        print("--sample-count must be >= 1", file=sys.stderr)
        return 2

    scenarios = _build_single_scenarios(args)
    report: dict[str, Any] = {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "api_base": args.api_base,
        "nb_container": args.nb_container,
        "mode": args.mode,
        "sample_count": args.sample_count,
        "sample_interval": args.sample_interval,
        "bridge": args.bridge,
        "switch_target": args.switch_target,
        "router_target": args.router_target,
        "resource_type": args.resource_type,
        "rounds": [],
    }

    print("Scenario plan:")
    for scenario in scenarios:
        print(
            "  - "
            f"{scenario.name}: "
            f"resource_type={scenario.resource_type} "
            f"target_name={scenario.target_name}"
        )
    print(f"Rounds: {args.sample_count}")
    print(
        "Compatibility note: "
        f"--nb-container={args.nb_container!r} is accepted for backward compatibility only; "
        "resource create/delete is now handled by the trace API."
    )

    try:
        for round_index in range(1, args.sample_count + 1):
            print(f"\n===== Round {round_index}/{args.sample_count} =====")
            round_record: dict[str, Any] = {
                "round": round_index,
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "scenarios": [],
            }

            for scenario_index, scenario in enumerate(scenarios, start=1):
                print(f"\n=== Scenario {scenario_index}/{len(scenarios)}: {scenario.name} ===")
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
                round_record["scenarios"].append(scenario_record)
                _print_snapshot(f"round {round_index} {scenario.name} before", scenario_record["metrics_before"])
                _print_trace_result(f"round {round_index} {scenario.name} trace", scenario_record["trace_result"])
                _print_snapshot(f"round {round_index} {scenario.name} after", scenario_record["metrics_after"])

                is_last_scenario = scenario_index == len(scenarios)
                is_last_round = round_index == args.sample_count
                if not (is_last_scenario and is_last_round):
                    time.sleep(args.sample_interval)

            report["rounds"].append(round_record)
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
        print(f"Unexpected latency probe runner error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("\nSummary")
    for round_record in report["rounds"]:
        for scenario_record in round_record["scenarios"]:
            result = scenario_record["trace_result"]
            print(
                "  "
                f"round={round_record['round']} "
                f"scenario={scenario_record['scenario']['name']} "
                f"status={result['status']} "
                f"command={result['command_latency_ms']}ms "
                f"nb_to_sb={result.get('nb_to_sb_latency_ms')}ms "
                f"sb_to_openflow={result.get('sb_to_openflow_latency_ms')}ms "
                f"total={result.get('total_latency_ms')}ms"
            )

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote probe artifact to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

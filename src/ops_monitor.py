#!/usr/bin/env python3
"""Generic Prometheus-to-status adapter for JamPeter Ops Monitor."""

from __future__ import annotations

import argparse
import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OPERATORS = {
    ">=": lambda value, threshold: value >= threshold,
    ">": lambda value, threshold: value > threshold,
    "<=": lambda value, threshold: value <= threshold,
    "<": lambda value, threshold: value < threshold,
    "==": lambda value, threshold: value == threshold,
    "!=": lambda value, threshold: value != threshold,
}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("unsupported config schema")
    if not isinstance(data.get("checks"), list):
        raise ValueError("checks must be a list")
    return data


class PrometheusClient:
    def __init__(self, base_url: str, timeout: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def query(self, expression: str) -> list[float]:
        params = urllib.parse.urlencode({"query": expression})
        request = urllib.request.Request(
            f"{self.base_url}/api/v1/query?{params}",
            headers={"User-Agent": "jampeter-ops-monitor/1"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.load(response)

        if payload.get("status") != "success":
            raise ValueError("Prometheus query did not succeed")

        data = payload.get("data", {})
        result_type = data.get("resultType")
        result = data.get("result")

        if result_type == "scalar":
            if not isinstance(result, list) or len(result) != 2:
                return []
            return [float(result[1])]

        if result_type != "vector" or not isinstance(result, list):
            return []

        values: list[float] = []
        for sample in result:
            value = sample.get("value") if isinstance(sample, dict) else None
            if not isinstance(value, list) or len(value) != 2:
                continue
            values.append(float(value[1]))
        return values


def reduce_values(values: list[float], reducer: str) -> float | None:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return None
    if reducer == "first":
        return finite[0]
    if reducer == "min":
        return min(finite)
    if reducer == "max":
        return max(finite)
    if reducer == "sum":
        return sum(finite)
    if reducer == "avg":
        return sum(finite) / len(finite)
    raise ValueError(f"unsupported reducer: {reducer}")


def evaluate_check(
    client: PrometheusClient, definition: dict[str, Any], observed_at: str
) -> dict[str, Any]:
    check_id = str(definition["id"])
    name = str(definition.get("name") or check_id)
    group = str(definition.get("group") or "runtime")
    fail_status = str(definition.get("fail_status") or "DEGRADED")
    missing_status = str(definition.get("missing_status") or "UNKNOWN")
    reducer = str(definition.get("reducer") or "first")
    operator = str(definition["operator"])
    threshold = float(definition["threshold"])

    if operator not in OPERATORS:
        raise ValueError(f"unsupported operator: {operator}")

    try:
        values = client.query(str(definition["query"]))
        value = reduce_values(values, reducer)
    except (OSError, TimeoutError, ValueError) as exc:
        return {
            "id": check_id,
            "name": name,
            "group": group,
            "status": "UNKNOWN",
            "summary": f"Monitoring query unavailable: {type(exc).__name__}.",
            "observed_at": observed_at,
        }

    if value is None:
        return {
            "id": check_id,
            "name": name,
            "group": group,
            "status": missing_status,
            "summary": "No finite monitoring sample was returned.",
            "observed_at": observed_at,
        }

    passed = OPERATORS[operator](value, threshold)
    status = "PASS" if passed else fail_status
    unit = str(definition.get("unit") or "")
    rendered = f"{value:g}{unit}"
    summary = (
        f"Observed {rendered}; expected {operator} {threshold:g}{unit}."
        if passed
        else f"Observed {rendered}; threshold {operator} {threshold:g}{unit} not met."
    )
    return {
        "id": check_id,
        "name": name,
        "group": group,
        "status": status,
        "summary": summary,
        "observed_at": observed_at,
        "value": value,
        "unit": unit,
    }


def summarize(systems: list[dict[str, Any]]) -> tuple[str, dict[str, int]]:
    statuses = ("PASS", "UNKNOWN", "DEGRADED", "BLOCKED")
    counts = {
        status: sum(1 for system in systems if system.get("status") == status)
        for status in statuses
    }
    if counts["BLOCKED"]:
        overall = "BLOCKED"
    elif counts["DEGRADED"]:
        overall = "DEGRADED"
    elif counts["UNKNOWN"]:
        overall = "UNKNOWN"
    else:
        overall = "PASS"
    return overall, counts


def build_snapshot(
    client: PrometheusClient, config: dict[str, Any]
) -> dict[str, Any]:
    observed_at = utc_now()
    systems = [
        evaluate_check(client, definition, observed_at)
        for definition in config["checks"]
    ]
    overall, counts = summarize(systems)
    return {
        "schema_version": 1,
        "kind": "ops-monitor-snapshot",
        "generated_at": observed_at,
        "overall_status": overall,
        "counts": counts,
        "systems": systems,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prometheus-url", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("monitor-snapshot.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    snapshot = build_snapshot(PrometheusClient(args.prometheus_url), config)
    args.output.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "OPS_MONITOR="
        f"{snapshot['overall_status']} "
        f"pass={snapshot['counts']['PASS']} "
        f"degraded={snapshot['counts']['DEGRADED']} "
        f"blocked={snapshot['counts']['BLOCKED']} "
        f"unknown={snapshot['counts']['UNKNOWN']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

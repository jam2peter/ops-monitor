# JamPeter Ops Monitor

JamPeter Ops Monitor is the monitoring adapter for the **OBSERVE** layer of the
JamPeter Ops Stack.

It does **not** replace Prometheus, Grafana, exporters or log systems. It turns
allowlisted Prometheus queries into a small, sanitized operational status
snapshot that another component can consume.

## Role

```text
Prometheus / exporters / existing telemetry
                  |
                  v
           JamPeter Ops Monitor
                  |
                  v
        sanitized status snapshot
                  |
                  v
          JamPeter Watchdog
```

The monitoring engine stays where it already belongs. Ops Monitor is only the
normalization boundary.

## What it answers

- Is a monitored condition healthy now?
- Is a threshold crossed?
- Is telemetry missing?
- What is the current PASS / DEGRADED / BLOCKED / UNKNOWN summary?

Ops Audit answers a different question: whether workflows, governance,
deployments, quotas and operational controls are coherent.

## Quick start

```bash
python3 src/ops_monitor.py \
  --prometheus-url http://127.0.0.1:9090 \
  --config examples/config.json \
  --output monitor-snapshot.json
```

The URL above is only a local example. Do not commit private infrastructure
addresses or credentials.

## Configuration

Each check declares a PromQL expression, reducer, comparison operator and
threshold. The emitted snapshot deliberately omits the PromQL expression and
source URL, so downstream consumers do not need private monitoring details.

Supported reducers:

```text
first min max avg sum
```

Supported comparisons:

```text
>= > <= < == !=
```

## Security

- no credentials are stored;
- no arbitrary remote administration;
- no automatic remediation;
- output contains normalized states, not raw logs;
- deployment-specific queries and endpoints remain private configuration;
- a query error is reported generically and does not leak exception text.

## JamPeter Ops Stack

Ops Monitor is the **MONITOR** module inside the cross-cutting **OBSERVE** layer:

```text
OBSERVE
├── AUDIT   -> JamPeter Ops Audit
├── MONITOR -> JamPeter Ops Monitor
└── ALERT   -> JamPeter Watchdog
```

## Tests

```bash
python3 -m compileall -q src tests
python3 -m unittest discover -s tests -v
python3 -m json.tool examples/config.json >/dev/null
```

## Status

Initial public product: source-only adapter. Adoption by a private runtime is a
separate deployment decision and must not be inferred from source CI.

## License

MIT

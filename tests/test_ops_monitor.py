import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import ops_monitor


class OpsMonitorTests(unittest.TestCase):
    def test_reduce_values(self):
        self.assertEqual(ops_monitor.reduce_values([2.0, 4.0], "min"), 2.0)
        self.assertEqual(ops_monitor.reduce_values([2.0, 4.0], "max"), 4.0)
        self.assertEqual(ops_monitor.reduce_values([2.0, 4.0], "avg"), 3.0)

    def test_pass_and_degraded(self):
        client = mock.Mock()
        client.query.return_value = [0.95]
        definition = {
            "id": "availability",
            "name": "Availability",
            "query": "up",
            "operator": ">=",
            "threshold": 1,
            "fail_status": "DEGRADED",
        }
        result = ops_monitor.evaluate_check(client, definition, "now")
        self.assertEqual(result["status"], "DEGRADED")
        self.assertEqual(result["value"], 0.95)

        client.query.return_value = [1.0]
        result = ops_monitor.evaluate_check(client, definition, "now")
        self.assertEqual(result["status"], "PASS")

    def test_missing_sample_is_unknown(self):
        client = mock.Mock()
        client.query.return_value = []
        result = ops_monitor.evaluate_check(
            client,
            {
                "id": "x",
                "query": "up",
                "operator": ">=",
                "threshold": 1,
            },
            "now",
        )
        self.assertEqual(result["status"], "UNKNOWN")

    def test_query_error_is_unknown_and_sanitized(self):
        client = mock.Mock()
        client.query.side_effect = OSError("private detail")
        result = ops_monitor.evaluate_check(
            client,
            {
                "id": "x",
                "query": "private_metric",
                "operator": ">=",
                "threshold": 1,
            },
            "now",
        )
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertNotIn("private detail", result["summary"])
        self.assertNotIn("private_metric", json.dumps(result))

    def test_snapshot_shape(self):
        client = mock.Mock()
        client.query.side_effect = [[1.0], [80.0]]
        config = {
            "schema_version": 1,
            "checks": [
                {"id": "up", "query": "up", "operator": ">=", "threshold": 1},
                {
                    "id": "capacity",
                    "query": "capacity",
                    "operator": "<",
                    "threshold": 90,
                },
            ],
        }
        snapshot = ops_monitor.build_snapshot(client, config)
        self.assertEqual(snapshot["kind"], "ops-monitor-snapshot")
        self.assertEqual(snapshot["overall_status"], "PASS")
        self.assertEqual(len(snapshot["systems"]), 2)

    def test_config_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text('{"schema_version":2,"checks":[]}', encoding="utf-8")
            with self.assertRaises(ValueError):
                ops_monitor.load_config(path)


if __name__ == "__main__":
    unittest.main()

"""Métricas vía CloudWatch Embedded Metric Format: basta con escribir a stdout."""
from __future__ import annotations

import json
import time


def emit(metrics: dict[str, float], dimensions: dict[str, str] | None = None,
         namespace: str = "PyGuardian") -> None:
    dims = dimensions or {}
    print(json.dumps({
        "_aws": {"Timestamp": int(time.time() * 1000),
                 "CloudWatchMetrics": [{"Namespace": namespace,
                                        "Dimensions": [list(dims)] if dims else [[]],
                                        "Metrics": [{"Name": k, "Unit": "Count"} for k in metrics]}]},
        **dims, **metrics}))

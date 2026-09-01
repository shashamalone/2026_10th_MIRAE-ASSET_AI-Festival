#!/usr/bin/env python3
"""실험 7: route guard와 실제 pyoxigraph vertical slice 결과 저장."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "results/metrics.json"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "script"))

from test_graph_vertical_slice import metrics as graph_metrics  # noqa: E402


def main() -> None:
    def run(*args: str):
        python = shutil.which("python3") or sys.executable
        return subprocess.run([python, *args], cwd=ROOT, text=True, capture_output=True)

    route = run(str(ROOT / "script/test_route_guard.py"))
    catalog = run(str(ROOT / "src/kb/build_schema_catalog.py"), "--check")
    rdb = run(str(ROOT / "script/test_rdb_vertical_slice.py"))
    graph = graph_metrics()
    result = {"route_guard_pass": route.returncode == 0,
              "route_guard_output": (route.stdout + route.stderr).strip(),
              "schema_cutoff_gate_pass": catalog.returncode == 0,
              "schema_cutoff_gate_output": (catalog.stdout + catalog.stderr).strip(),
              "rdb_regression_pass": rdb.returncode == 0,
              "rdb_regression_output": (rdb.stdout + rdb.stderr).strip(),
              "graph": graph,
              "overall": "BLOCKED" if (catalog.returncode or rdb.returncode or
                                         not graph["graph_only_promotion_ready"]) else "PASS"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

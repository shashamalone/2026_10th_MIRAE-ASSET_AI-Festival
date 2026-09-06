from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC))

from kb import config  # noqa: E402
from tools import graph_schema  # noqa: E402


class ConfigPathTests(unittest.TestCase):
    def test_repository_paths_point_to_canonical_directories(self) -> None:
        self.assertEqual(config.ROOT, REPO_ROOT)
        self.assertEqual(config.ONTOLOGY_DIR, REPO_ROOT / "ontology")
        self.assertEqual(config.ARTIFACTS, REPO_ROOT / "artifacts")
        self.assertEqual(
            graph_schema.SCHEMA_INDEX_PATH,
            REPO_ROOT / "artifacts" / "graph_schema_index.json",
        )
        self.assertTrue(config.ONTOLOGY_DIR.is_dir())
        for filename in graph_schema.TBOX_FILES:
            self.assertTrue((config.ONTOLOGY_DIR / filename).is_file(), filename)

    def test_schema_catalog_loads_all_tboxes_without_url_fallback(self) -> None:
        graph_schema.catalog.cache_clear()
        catalog = graph_schema.catalog()

        self.assertGreater(len(catalog.classes), 0)
        self.assertGreater(len(catalog.properties), 0)
        self.assertGreater(len(catalog.graph), 0)

    def test_config_is_independent_of_current_working_directory(self) -> None:
        code = (
            "import json,sys; "
            f"sys.path.insert(0, {str(SRC)!r}); "
            "from kb.config import ROOT,ONTOLOGY_DIR,ARTIFACTS; "
            "print(json.dumps([str(ROOT),str(ONTOLOGY_DIR),str(ARTIFACTS)]))"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True,
                env=os.environ.copy(),
            )
        self.assertEqual(
            json.loads(completed.stdout),
            [str(REPO_ROOT), str(REPO_ROOT / "ontology"), str(REPO_ROOT / "artifacts")],
        )

    def test_latency_harness_catalog_initialization_succeeds(self) -> None:
        harness = REPO_ROOT / "test" / "pipline-test" / "latency" / "run_latency.py"
        source = harness.read_text(encoding="utf-8")
        self.assertIn("_CatalogCls = type(graph_schema.catalog())", source)

        catalog = graph_schema.catalog()
        self.assertIs(type(catalog), graph_schema.SchemaCatalog)


if __name__ == "__main__":
    unittest.main()

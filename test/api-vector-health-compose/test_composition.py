# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SPEC = importlib.util.spec_from_file_location("audit_composition", HERE / "audit_composition.py")
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class CompositionAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (ROOT / "src" / "api.py").read_text(encoding="utf-8")

    def test_current_source_passes_every_composition_check(self):
        result = AUDIT.audit_source(self.source)
        self.assertTrue(result["overall_pass"], result["checks"])
        self.assertEqual(len(result["observed"]["routes"]), 9)
        self.assertEqual(len(result["observed"]["vector_tables"]), 7)

    def test_stale_graph_default_is_rejected(self):
        mutated = self.source.replace('"1226698"', '"1169374"', 1)
        result = AUDIT.audit_source(mutated)
        self.assertFalse(result["checks"]["canonical_graph_default"])
        self.assertFalse(result["overall_pass"])

    def test_escaped_text_nul_check_is_rejected(self):
        mutated = self.source.replace(
            'if "\\x00" in statement:',
            'if "\\\\x00" in statement:',
            1,
        )
        self.assertNotEqual(mutated, self.source)
        result = AUDIT.audit_source(mutated)
        self.assertFalse(result["checks"]["actual_nul_guard"])
        self.assertFalse(result["overall_pass"])

    def test_pending_vector_readiness_is_rejected(self):
        mutated = self.source.replace(
            'vector.get("ready") is True',
            'vector.get("status") in {"pending", "ready"}',
            1,
        )
        result = AUDIT.audit_source(mutated)
        self.assertFalse(result["checks"]["health_requires_strict_vector_ready"])
        self.assertFalse(result["overall_pass"])


if __name__ == "__main__":
    unittest.main()

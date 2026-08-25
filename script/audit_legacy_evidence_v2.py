from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
runpy.run_module("kb.audit_legacy_evidence_v2", run_name="__main__")

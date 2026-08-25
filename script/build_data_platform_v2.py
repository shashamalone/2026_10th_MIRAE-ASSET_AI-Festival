# -*- coding: utf-8 -*-
"""저장소 루트용 PostgreSQL v2 stage 빌더 래퍼."""
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
runpy.run_module("kb.build_data_platform_v2", run_name="__main__")

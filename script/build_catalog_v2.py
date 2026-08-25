# -*- coding: utf-8 -*-
"""저장소 루트에서 실행하는 v2 카탈로그 빌더 래퍼."""
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
runpy.run_module("kb.build_catalog_v2", run_name="__main__")

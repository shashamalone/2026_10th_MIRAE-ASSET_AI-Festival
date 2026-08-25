# -*- coding: utf-8 -*-
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
runpy.run_module("kb.build_vectors_v2", run_name="__main__")

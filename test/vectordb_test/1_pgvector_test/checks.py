# -*- coding: utf-8 -*-
"""테스트 프레임워크 없이 PASS/FAIL 을 찍고 exit code 로 넘긴다."""
import sys

_FAILS = []


def check(name, cond, detail=""):
    ok = bool(cond)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        _FAILS.append(name)
    return ok


def finish(title):
    if _FAILS:
        print(f"\n{title}: FAIL ({len(_FAILS)}건) — {', '.join(_FAILS)}")
        sys.exit(1)
    print(f"\n{title}: PASS")
    sys.exit(0)

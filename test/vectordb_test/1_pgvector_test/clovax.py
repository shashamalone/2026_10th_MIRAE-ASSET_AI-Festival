# -*- coding: utf-8 -*-
"""저장소의 검증된 clova.py 를 '그대로' 로드한다. 새 CLOVA 클라이언트가 아니다.

지시서는 "저장소 루트의 clova.py 를 sys.path 로 import" 하라고 했지만, 현재 체크아웃된
브랜치(69f5c9a)의 작업트리에는 clova.py 가 없다 — agent/·tools/·script/ 에도 __pycache__ 만
남아 있다. 같은 저장소의 커밋 46ac51a(feature/ontology-definition)에는 그대로 있으므로,

  1) 루트에 clova.py 가 있으면 그것을 쓴다 (지시서가 의도한 경로).
  2) 없으면 git 블롭에서 바이트 그대로 꺼내 _vendor/ 에 캐시해 로드한다.

어느 쪽이든 embed()/embed_many() 구현은 저장소 원본이다. 여기서 재구현하지 않는다.
"""
import importlib.util
import subprocess
import sys

from config import ROOT

_VENDOR = ROOT / "vectordb_test" / "_vendor"
_BLOB = "46ac51a:clova.py"          # feature/ontology-definition 의 MVP 커밋


def _source():
    # 08-22 이전으로 clova.py 가 src/ 아래로 옮겨졌다. src/ 를 먼저 본다.
    # 이 순서를 빼면 루트에 파일이 없어 아래 git 블롭 폴백으로 조용히 떨어지고,
    # 하네스가 작업트리가 아니라 08-21 커밋 사본을 쓰게 된다(실제로 그랬다).
    for cand, origin in ((ROOT / "src" / "clova.py", "src/"),
                         (ROOT / "clova.py", "저장소 루트")):
        if cand.exists():
            return cand, origin
    _VENDOR.mkdir(parents=True, exist_ok=True)
    cached = _VENDOR / "clova.py"
    if not cached.exists():
        cached.write_bytes(
            subprocess.check_output(["git", "-C", str(ROOT), "show", _BLOB])
        )
    return cached, f"git {_BLOB}"


SRC, ORIGIN = _source()

_spec = importlib.util.spec_from_file_location("clova_repo", SRC)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["clova_repo"] = _mod
_spec.loader.exec_module(_mod)

embed = _mod.embed
embed_many = _mod.embed_many

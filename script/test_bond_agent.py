# -*- coding: utf-8 -*-
"""채권 에이전트 end-to-end 실행.

    python3 script/test_bond_agent.py
"""
import sys
import time
from pathlib import Path

# 런타임 모듈(agent/tools/config/clova)은 저장소 루트가 아니라 src/ 아래에 있다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from agent.agent_core import ask  # noqa: E402

QUESTIONS = ["채권의 위험등급은 어떻게 정의돼?",
             "듀레이션은 뭐야?",
             "듀레이션이 길면 어떤 의미야?",
             "채권 금리위험이 뭐야?"]

if __name__ == "__main__":
    for q in QUESTIONS:
        t0 = time.time()
        out = ask(q)
        i = out["intent"]
        print("=" * 78)
        print(f"QUESTION  {q}   [{time.time()-t0:.2f}s]")
        print(f"INTENT    {i.get('domain')} / {i.get('intent')}  keywords={i.get('keywords')}"
              + (f"  ⚠ {i['error']}" if i.get("error") else ""))
        print("TOP HITS")
        for n, h in enumerate(out["schema_hits"], 1):
            print(f"  {n}. {h['score']:.3f}  {h['term_uri']:<28} {h['label']}")
        print(f"ANSWER\n{out['answer']}\n")

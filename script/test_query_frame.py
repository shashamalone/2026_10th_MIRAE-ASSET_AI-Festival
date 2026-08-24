#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""1단계 Query Frame 자기검사.

    python3 script/test_query_frame.py           # guard·렌더러만 (네트워크 불필요)
    python3 script/test_query_frame.py --live    # CLOVA 왕복 1건 추가

guard 는 장식이 아니라 계약이다. 실측에서 결정적 규칙 두 개가 프롬프트로 못 잡던 것을
잡았다 — 단일값 in → == 로 operator 88%→100%, 날짜 없는 as_of → latest_snapshot 으로
temporal 94.1%→100%. 그 규칙들이 살아 있는지 여기서 지킨다.
전체 35문항 측정은 vectordb_test/5_query_frame_v1/eval_query_frame.py 가 한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from agent import query_frame as qf  # noqa: E402


def test_guard():
    g = qf.guard({
        "task": "용어정의",                                   # enum 밖
        "domain_candidates": ["bond_kr", "BOND"],             # 절반이 enum 밖
        "constraints": [
            {"raw": "AA- 이상", "field_text": "신용등급", "operator": "이상",
             "value_text": "AA-", "kind": "categorical", "grounding_status": "resolved"},
            {"raw": "회사채", "field_text": "채권 종류", "operator": "in",
             "value_text": "회사채", "kind": "categorical", "grounding_status": "resolved"},
            {"raw": "안전한", "field_text": "안전한", "operator": "exists",
             "kind": "qualitative", "grounding_status": "resolved"},
        ],
        "ordering": [{"field_text": "매수수익률", "direction": "높은 순"}],
        "limit": "10",
        "temporal": {"kind": "as_of", "raw": "현재", "as_of_text": None, "window_text": None},
    })
    assert set(qf.FIELDS) <= set(g), "guard 는 14필드를 모두 채운다"
    assert g["domain_candidates"] == ["bond_kr"]
    assert g["constraints"][0]["operator"] == ">=", "이상 → >="
    assert g["constraints"][1]["operator"] == "==", "값이 하나뿐인 in 은 == 다"
    assert g["constraints"][2]["grounding_status"] == "unresolved", \
        "qualitative 는 resolved 일 수 없다 — premature grounding 방지선"
    assert g["ordering"][0]["direction"] == "desc"
    assert g["limit"] == 10 and isinstance(g["limit"], int)
    assert g["temporal"]["kind"] == "latest_snapshot", "날짜 없는 as_of 는 최신 스냅샷이다"
    assert g["task"] == "filter_rank", "지목한 상품이 없으면 lookup 일 수 없다"
    assert len(g["_guard"]) >= 6, g["_guard"]
    return g


def test_leaks():
    # D4 — 1단계는 TBox 도 물리 스키마도 안 본다
    assert qf.leaks({"requested_fields": [{"text": "crd_grd_rank"}]}) == ["crd_grd_rank"]
    assert qf.leaks({"constraints": [{"field_text": "fp:ratingRank"}]})
    assert qf.leaks({"relations": [{"raw": "", "path": ["기업", "parent_company"]}]})
    assert qf.leaks({"targets": [{"text": "회사채"}], "ordering": [{"field_text": "매수수익률"}]}) == []


def test_to_conditions(g):
    # 3단계 Planner 계약 (wanggyu/agent/state.py: decomposed_conditions: list[str])
    conds = qf.to_conditions(g)
    assert any("신용등급 >= AA-" in c for c in conds), conds
    assert any("기준 미확정" in c for c in conds), "모호 조건은 그렇다고 표시돼야 한다"
    assert any("매수수익률 DESC" in c for c in conds), conds
    assert all(isinstance(c, str) for c in conds)
    return conds


def test_abstain_map():
    assert set(qf.ABSTAIN_CODE) == set(qf.VALIDATION_TYPES), "검증 유형 5종과 1:1 이어야 한다"
    assert all(v.startswith("ABSTAIN_") for v in qf.ABSTAIN_CODE.values()), "정본은 긴 형식이다"


if __name__ == "__main__":
    g = test_guard()
    test_leaks()
    conds = test_to_conditions(g)
    test_abstain_map()
    print(f"query_frame 자기검사 PASS — schema {qf.SCHEMA_VERSION}, "
          f"{len(qf.FIELDS)}필드, guard 보정 {len(g['_guard'])}건")
    for c in conds:
        print("   ", c)

    if "--live" in sys.argv:
        q = "판매 중인 특수채 중 A 이상인 종목을 잔존일수 짧은 순으로 2개 알려줘"
        f = qf.extract(q)
        assert set(qf.FIELDS) <= set(f)
        assert f["limit"] == 2, f["limit"]
        assert f["ordering"] and f["ordering"][0]["direction"] == "asc", f["ordering"]
        assert not qf.leaks(f), qf.leaks(f)
        print(f"\nlive PASS — task={f['task']} domain={f['domain_candidates']} "
              f"constraints={len(f['constraints'])} limit={f['limit']}")

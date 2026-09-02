# -*- coding: utf-8 -*-
"""2차 테스트 질의셋 — 실제 130개 용어 환경에서 검색 품질을 재기 위한 것.

원칙 셋:
1. 정답(gold)은 지어내지 않는다. 동의어 질의는 그 표현이 원문 텍스트에
   실제로 없는 것만 넣었다(`쿠폰금리`·`이자율`·`보수율`·`펀드 규모`·`구성종목` 0건 확인).
2. 레이블이 완전히 같은 16쌍(예: fp:RiskGrade / fp:hasRiskGrade)은
   손으로 나열하지 않고 데이터에서 자동으로 짝을 붙인다. 빠뜨릴 여지를 없앤다.
3. `noise` 는 정답이 없는 질의다. 여기서 0.45 를 넘는 용어가 나오면 오탐이다.
   `absent` 는 금융 질의지만 온톨로지에 용어가 없는 경우다 — 관련 개념이 걸리는 것
   자체는 설계상 정상이므로 오탐률에 넣지 않고 따로 본다.
"""
import json
from pathlib import Path

TERMS = Path(__file__).resolve().parent.parent / "artifacts" / "bond_terms.json"
_T = json.loads(TERMS.read_text(encoding="utf-8"))
LABEL = {t["term_uri"]: t["label"] for t in _T}


def _twins():
    """레이블이 완전히 같은 용어끼리 묶는다. gold 의 쌍둥이는 관대 채점에서 정답 취급."""
    by = {}
    for u, l in LABEL.items():
        by.setdefault(l, []).append(u)
    out = {}
    for group in by.values():
        for u in group:
            out[u] = set(group)
    return out


TWIN = _twins()


def _family(kw):
    """레이블에 특정 어휘가 든 용어 전부. 부분어 질의의 '어군' 정답에 쓴다."""
    return {u for u, l in LABEL.items() if kw in l}


# (분류, 질의, gold, 추가 허용)  gold=None 이면 정답 없음
RAW = [
    # ── 정확 용어: 레이블을 그대로 친 경우 ────────────────────────────────
    ("exact", "표면금리", "fp:couponRate", set()),
    ("exact", "듀레이션", "fp:duration", set()),
    ("exact", "잔존일수", "fp:remainingDays", set()),
    ("exact", "순자산총액", "fp:netAssets", set()),
    ("exact", "총보수요율", "fp:expenseRatio", set()),
    ("exact", "편입비중", "fp:weight", set()),
    ("exact", "지분율", "fp:ownershipPct", set()),
    ("exact", "발행잔액", "fp:issuedAmount", set()),
    ("exact", "상장일", "fp:listingDate", set()),
    ("exact", "테마명", "fp:themeName", set()),
    ("exact", "지수명", "fp:indexName", set()),
    ("exact", "신용등급 서열", "fp:ratingRank", set()),

    # ── 자연어: 조사·의문문. 실제 사용자가 던지는 모양 ─────────────────────
    ("natural", "듀레이션이 뭐야?", "fp:duration", set()),
    ("natural", "이 채권 만기가 언제야?", "fp:maturityDate", set()),
    ("natural", "표면금리는 어떻게 되나요?", "fp:couponRate", set()),
    ("natural", "이 ETF 총보수 얼마야?", "fp:expenseRatio", set()),
    ("natural", "순자산이 얼마나 되나요?", "fp:netAssets", set()),
    ("natural", "이 상품은 누가 운용하나요?", "fp:managedBy", set()),
    ("natural", "어느 회사가 발행했나요?", "fp:issuedBy", {"fp:Issuer"}),
    ("natural", "위험등급이 몇 등급인가요?", "fp:riskGradeLevel", {"fp:RiskGrade", "fp:hasRiskGrade"}),
    ("natural", "만기까지 며칠이나 남았어?", "fp:remainingDays", set()),
    ("natural", "어떤 지수를 따라가나요?", "fp:tracksIndex", {"fp:Index", "fp:indexName"}),
    ("natural", "이 채권에 담보가 잡혀 있나요?", "fp:hasCollateralType", set()),
    ("natural", "지금 살 수 있는 상품인가요?", "fp:isSellable", {"fp:onSale", "fp:hasSaleInfo"}),

    # ── 동의어: 원문에 그 표현이 없다(사전 확인 완료) ──────────────────────
    ("synonym", "채권 이자율", "fp:couponRate", set()),
    ("synonym", "쿠폰금리", "fp:couponRate", set()),
    ("synonym", "보수율", "fp:expenseRatio", set()),
    ("synonym", "펀드 규모", "fp:netAssets", set()),
    ("synonym", "신용평가 등급", "fp:CreditRating", {"fp:creditRatingLabel", "fp:hasCreditRating"}),
    ("synonym", "구성종목", "fp:holdingSecurity", {"fp:Holding", "fp:hasHolding"}),
    ("synonym", "상품 이름", "fp:productName", {"fp:productShortName"}),
    ("synonym", "투자 자산 종류", "fp:AssetType", set()),
    ("synonym", "어느 나라에 투자하나요", "fp:InvestmentRegion", set()),
    ("synonym", "자회사 지분을 얼마나 갖고 있나", "fp:ownershipPct", set()),

    # ── 부분어: 복합명사의 일부. 정답이 하나로 안 정해져 '어군'으로 채점 ────
    ("partial", "등급", None, _family("등급")),
    ("partial", "만기", None, _family("만기")),
    ("partial", "수익률", None, _family("수익률")),
    ("partial", "보수", None, _family("보수")),
    ("partial", "지수", None, _family("지수")),
    ("partial", "테마", None, _family("테마")),
    ("partial", "담보", None, _family("담보")),
    ("partial", "발행", None, _family("발행")),

    # ── 혼동군: 실제 130개 환경에서 서로 경쟁하는 용어들 ───────────────────
    ("confuse", "채권 신용등급", "fp:CreditRating", {"fp:creditRatingLabel", "fp:hasCreditRating"}),
    ("confuse", "투자위험등급", "fp:RiskGrade", set()),
    ("confuse", "위험등급 수준", "fp:riskGradeLevel", set()),
    ("confuse", "신용등급 대역", "fp:RatingBand", set()),
    ("confuse", "신용등급 표기", "fp:creditRatingLabel", set()),
    ("confuse", "평가사별 등급이 서로 일치하나요", "fp:ratingAgreement", set()),
    ("confuse", "평가사 등급이 몇 개인가요", "fp:ratingAgencyCount", set()),
    ("confuse", "만기일", "fp:maturityDate", set()),
    ("confuse", "잔존만기 구간", "fp:maturityBucket", set()),
    ("confuse", "1년 수익률", "fp:return1Y", set()),
    ("confuse", "연초이후 수익률", "fp:returnYTD", set()),
    ("confuse", "3개월 수익률", "fp:return3M", set()),
    ("confuse", "매수수익률", "fp:buyYield", set()),
    ("confuse", "적용수익률", "fp:appliedYield", set()),
    ("confuse", "채권 발행사", "fp:issuedBy", {"fp:Issuer"}),
    ("confuse", "문서 발행처", "fp:documentPublisher", set()),
    ("confuse", "발행일", "fp:issueDate", set()),
    ("confuse", "문서 발행일", "fp:documentPublishedDate", set()),

    # ── 완전 무관: 정답 없음. 0.45 를 넘으면 오탐 ─────────────────────────
    ("noise", "오늘 점심 뭐 먹지", None, set()),
    ("noise", "주차장 어디에 있나요", None, set()),
    ("noise", "파이썬 리스트 정렬하는 방법", None, set()),
    ("noise", "서울 날씨 알려줘", None, set()),
    ("noise", "어제 축구 경기 결과", None, set()),
    ("noise", "이 영화 재미있나요", None, set()),
    ("noise", "병원 예약하고 싶어요", None, set()),
    ("noise", "비트코인 시세 알려줘", None, set()),

    # ── 온톨로지 부재: 금융 질의지만 해당 용어가 없다. 오탐률에 넣지 않는다 ──
    ("absent", "만기수익률 YTM이 얼마인가요", None, set()),
    ("absent", "신용등급 AAAA인 채권", None, set()),
    ("absent", "샤프지수 알려줘", None, set()),
    ("absent", "베타 계수가 얼마인가요", None, set()),
]


def queryset():
    """gold 의 '레이블 쌍둥이'를 관대 정답에 자동 합류시킨다."""
    out = []
    for cat, q, gold, extra in RAW:
        lenient = set(extra)
        if gold:
            lenient |= TWIN.get(gold, set())
            lenient.add(gold)
        out.append({"category": cat, "query": q, "gold": gold, "lenient": lenient})
    return out


if __name__ == "__main__":
    import collections
    qs = queryset()
    c = collections.Counter(q["category"] for q in qs)
    print(f"질의 {len(qs)}건")
    for k in ("exact", "natural", "synonym", "partial", "confuse", "noise", "absent"):
        print(f"  {k:<9}{c[k]:>3}")
    bad = [q for q in qs if q["gold"] and q["gold"] not in LABEL]
    print("존재하지 않는 gold:", bad or "없음")

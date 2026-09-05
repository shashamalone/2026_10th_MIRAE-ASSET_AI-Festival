#!/usr/bin/env python3
"""PROPERTY_STORAGE_MAP.csv + 트리거 어휘 → docs_data_layer/ABSTAIN_RULES.csv

    python3 script/build_abstain_rules.py

`storage=none` 9속성과 `domain_caveat` 9건을 **실행 가능한 판정 규칙**으로 바꾼다.
라우터는 이 표만 보고 검색·LLM 호출 전에 답변불가를 결정할 수 있다.

트리거 어휘는 손으로 작성했다 — TBox의 rdfs:label은 표준명 1개뿐이고 skos:altLabel이
속성 레벨에는 0건이라(2026-08-22 실측) 질의 표층형을 이을 사전이 없기 때문이다.
이 표의 trigger_ko는 그대로 **TBox altLabel 보강 후보**이기도 하다.

property·evidence는 PROPERTY_STORAGE_MAP.csv에서 가져온다. 판정 근거가 한 곳에만 있게 한다.
"""
import csv
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAP = ROOT / "docs_data_layer" / "PROPERTY_STORAGE_MAP.csv"
OUT = ROOT / "docs_data_layer" / "ABSTAIN_RULES.csv"

# action 의미
#   ABSTAIN — 검색 없이 즉시 답변불가
#   GUARD   — 해당 도메인만 답변불가로 잘라내고 나머지 도메인은 정상 답변
#   REWRITE — 다른 경로로 우회 가능. 답변불가로 처리하면 오답이다
RULES = [
    # ── Family A: 측정 축이 데이터에 아예 없다 (storage=none) ────────────────
    ("A", "hasDistributionType", "", "ABSTAIN", "AXIS_UNAVAILABLE",
     "월배당|분배금|배당주기|배당 ETF|인컴|분배율|배당수익률",
     "배당·분배 관련 컬럼이 전량 무효라 분배 유형을 판별할 수 없습니다"),
    ("A", "hasRedemptionType", "", "ABSTAIN", "AXIS_UNAVAILABLE",
     "개방형|폐쇄형|환매|환매수수료|환매기간|중도환매",
     "환매 유형 구분 축이 제공 데이터에 없습니다"),
    ("A", "hasIssuanceType", "", "ABSTAIN", "AXIS_UNAVAILABLE",
     "설정 유형|추가형|단위형|모자형|설정 방식",
     "설정 유형 코드의 의미가 확정되지 않아 판별할 수 없습니다"),
    ("A", "hasCollateralType", "", "ABSTAIN", "AXIS_UNAVAILABLE",
     "담보부|무담보|보증채|담보|보증|담보채",
     "담보·보증 분류 축이 채권 마스터에 없습니다"),
    ("A", "hasCustodian", "", "ABSTAIN", "AXIS_UNAVAILABLE",
     "수탁회사|수탁은행|신탁업자|수탁",
     "수탁 기관코드는 있으나 코드와 사명을 잇는 매핑표가 없습니다"),
    ("A", "hasIssuerCategory", "", "ABSTAIN", "AXIS_UNAVAILABLE",
     "발행사 업종|발행사 섹터|발행기업 산업|발행사 분류",
     "발행사는 명칭 문자열만 있어 업종을 구분할 수 없습니다"),
    ("A", "hasUnderlyingScope", "", "ABSTAIN", "AXIS_UNAVAILABLE",
     "기초자산 범위|편입 섹터|기초자산 유형|섹터 구성",
     "기초지수가 95.2% 결측이고 섹터명은 전량 결측입니다"),
    ("A", "belongsToIndustry", "", "ABSTAIN", "AXIS_UNAVAILABLE",
     "산업 분류|업종|산업군|섹터 분류",
     "기업의 산업 분류 축이 제공 데이터에 없습니다"),
    # 역방향 탐색으로 우회 가능하다. ABSTAIN 으로 처리하면 답할 수 있는 질문을 버린다.
    ("A", "subsidiaryOf", "", "REWRITE", "",
     "모회사|지배회사|어느 회사의 자회사|모기업",
     "fp:hasSubsidiary 역방향 탐색으로 우회한다 (관계 29,524행 보유)"),

    # ── Family B: 축은 있으나 특정 도메인에서 무효 (domain_caveat) ───────────
    ("B", "return1Y", "etf_gl", "GUARD", "AXIS_UNAVAILABLE",
     "수익률|성과|상승률|수익률 상위|가장 많이 오른|1년 수익",
     "해외ETF는 수익률 컬럼이 전량 0(미계산)이라 성과를 비교할 수 없습니다"),
    ("B", "leverageFactor", "etf_gl", "GUARD", "AXIS_UNAVAILABLE",
     "레버리지|2배|3배|배수|곱버스",
     "해외ETF는 레버리지 배수 컬럼이 전량 결측입니다 (인버스 여부는 fp:isInverse로 답변 가능)"),
    ("B", "onSale", "etf_gl", "GUARD", "AXIS_UNAVAILABLE",
     "판매 가능|살 수 있는|매수 가능|판매중",
     "해외ETF는 판매여부가 전 종목 동일값이라 필터로 기능하지 못합니다"),
    ("B", "tradingSuspended", "etf_gl", "GUARD", "AXIS_UNAVAILABLE",
     "거래정지|거래 중지|매매 정지",
     "해외ETF는 거래정지 플래그가 전 종목 동일값입니다"),
    ("B", "hasRiskGrade", "etf_gl", "GUARD", "AXIS_UNAVAILABLE",
     "위험등급|투자위험|위험도|안전한",
     "해외ETF에는 위험등급 컬럼이 없습니다"),
    ("B", "coreProduct", "etf_gl", "GUARD", "AXIS_UNAVAILABLE",
     "핵심상품|추천|대표상품|주력",
     "해외ETF에는 핵심상품 선정 값이 없습니다"),
    ("B", "expenseRatio", "ETN", "GUARD", "DOMAIN_VIOLATION",
     "총보수|보수|수수료|운용보수",
     "ETN은 총보수 개념이 없는 상품입니다"),
    ("B", "hasHolding", "ETN", "GUARD", "DOMAIN_VIOLATION",
     "편입종목|구성종목|담고 있는|들어간 종목|보유종목",
     "ETN은 편입종목 개념이 없는 상품입니다"),
    ("B", "agencyRatings", "bond_kr", "GUARD", "AXIS_UNAVAILABLE",
     "평가사별 등급|어느 평가사|신용평가사|평가기관",
     "평가기관명이 데이터에 없어 어느 기관이 매긴 등급인지 특정할 수 없습니다"),
]

HEADER = ["rule_id", "family", "property", "scope", "action", "abstain_code",
          "trigger_ko", "reason_template", "label", "storage", "availability", "evidence"]


def main() -> None:
    rows = {r["property"]: r for r in csv.DictReader(MAP.open(encoding="utf-8"))}
    out = []
    for i, (fam, prop, scope, action, code, trig, reason) in enumerate(RULES, 1):
        src = rows.get(prop, {})
        # 근거는 domain_caveat 우선(도메인 한정 문장), 없으면 comment 앞부분
        evidence = src.get("domain_caveat") or src.get("comment", "")[:160]
        out.append({
            "rule_id": f"{fam}{i:02d}", "family": fam, "property": prop, "scope": scope,
            "action": action, "abstain_code": code, "trigger_ko": trig,
            "reason_template": reason,
            "label": (src.get("label", "").split("|") or [""])[0],
            "storage": src.get("storage", ""), "availability": src.get("availability", ""),
            "evidence": evidence.replace("\n", " "),
        })
        if prop not in rows:
            print(f"  !! {prop} 가 PROPERTY_STORAGE_MAP 에 없다 — 매핑표를 먼저 재생성하라")

    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER)
        w.writeheader()
        w.writerows(out)

    print(f"wrote {OUT.relative_to(ROOT)}  ({len(out)} rules)")
    for key in ("family", "action", "abstain_code"):
        c = {}
        for r in out:
            c[r[key] or "(없음)"] = c.get(r[key] or "(없음)", 0) + 1
        print(f"  [{key}] " + ", ".join(f"{k}={v}" for k, v in sorted(c.items())))
    trig = sum(len(r["trigger_ko"].split("|")) for r in out)
    print(f"  트리거 표현 총 {trig}개 — TBox skos:altLabel 보강 후보")


if __name__ == "__main__":
    main()

"""
GraphDB 엔티티 해소에 쓰는 식별자 정규화
"""
from __future__ import annotations

import re
import unicodedata


_ORGANIZATION_ALIASES = {
    "에스케이": "SK",
    "엘지": "LG",
    "케이티": "KT",
    "지에스": "GS",
    "씨제이": "CJ",
    "에이치디": "HD",
    "에스디": "SD",
    "디비": "DB",
    "케이비": "KB",
    "엔에이치": "NH",
}
_LEGAL_FORM = re.compile(r"\(주\)|㈜|\(유\)|주식회사|유한회사")
_SEPARATORS = re.compile(r"[\s·,._\-]+")

# 사용자가 실제로 쓰는 한글 통칭과 관계 원천의 영문 종목명/식별자를 잇는
# 검토된 별칭이다. 부분 문자열 유사도나 LLM 번역을 실행 시점에 사용하지
# 않는다. 각 항목은 적재된 원천에서 직접 대조한 label/code만 허용한다.
#
# 캠브리콘: relations/etf_holding.csv 및 instances_company.ttl에서
# Cambricon / 688256 / CNE1000041R8 표기를 확인했다(holding as_of 2026-07-10).
_REVIEWED_HOLDING_SECURITY_ALIASES = {
    "캠브리콘": {
        "label_contains": ("cambricon",),
        "codes": (
            "688256 C1 EQUITY", "688256 C1 Equity",
            "688256 CH", "688256 CH Equity", "CNE1000041R8",
        ),
    },
    "cambricon": {
        "label_contains": ("cambricon",),
        "codes": (
            "688256 C1 EQUITY", "688256 C1 Equity",
            "688256 CH", "688256 CH Equity", "CNE1000041R8",
        ),
    },
}


def normalize_text(value: object) -> str:
    """표시 문자열 비교용 정규형. URI 생성에는 사용하지 않는다."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    return " ".join(text.split()).casefold()


def normalize_organization_name(value: object) -> str:
    """법인격·구분자와 검증된 한글 약칭 흔들림만 제거한다.

    편집거리 기반 유사명 대체는 하지 않는다. 같은 정규형이 여러 URI에 대응하면
    entity resolver가 모호성으로 중단해야 한다.
    """
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _LEGAL_FORM.sub("", text)
    text = _SEPARATORS.sub("", text)
    for source in sorted(_ORGANIZATION_ALIASES, key=len, reverse=True):
        text = text.replace(source, _ORGANIZATION_ALIASES[source])
    return text.upper()


def reviewed_holding_security_alias(value: object) -> dict[str, tuple[str, ...]] | None:
    """편입증권 통칭의 검토된 Graph label/code 묶음을 돌려준다.

    한 종목이 공급사별 Bloomberg suffix와 ISIN으로 여러 Security URI에
    나뉘어 적재될 수 있어 단일 URI로 임의 축약하지 않는다. 호출자는 이
    식별자 묶음과 실제 Graph label/code를 대조해 모든 해당 URI를 조회한다.
    등록되지 않은 통칭에는 ``None``을 반환해 일반 exact-first resolver의
    안전 계약을 그대로 유지한다.
    """
    key = normalize_text(value)
    spec = _REVIEWED_HOLDING_SECURITY_ALIASES.get(key)
    return {name: tuple(values) for name, values in spec.items()} if spec else None


def expand_organization_aliases(value: object) -> list[str]:
    """조직명 문자열의 검증된 표기 변형을 전부 만든다(RDB 텍스트 조건용).

    RDB 원천 데이터는 "에스케이하이닉스(주)"처럼 순한글 정식 표기를 쓰는데,
    질문/의도 분석은 "SK하이닉스"처럼 영문 약칭이 섞인 통칭을 쓰는 경우가
    많다 - 그대로 exact match를 걸면 0건으로 실패한다(2026-09-02 실측,
    "SK하이닉스가 발행한 채권" 질문에서 발견. 데이터는 실제로 존재했다).

    편집거리·유사도로 "비슷한 이름"을 짐작하지 않는다 - normalize_organization_name
    이 이미 쓰는 것과 같은 _ORGANIZATION_ALIASES 표 안의 치환만, 정방향(한글
    약칭->영문)과 역방향(영문->한글 약칭) 둘 다 적용해 원본을 포함한 변형
    목록을 만든다. 이 표에 없는 치환은 절대 만들지 않으므로 "엉뚱한 회사로
    대체" 위험이 없다.

    법인격 접미사("(주)" 등)는 여기서 붙이거나 떼지 않는다 - RDB 쪽 원본
    값에 어느 형태로 붙어 있는지 이 함수는 모른다. 그래서 반환된 변형은
    정확히 일치(=)가 아니라 LIKE 부분일치로 검색해야 한다
    (utils.format_resolved_schema의 org_name_variants 렌더링 참고)."""
    text = str(value or "").strip()
    if not text:
        return []
    variants = {text}
    substitutions = list(_ORGANIZATION_ALIASES.items()) + [
        (latin, korean) for korean, latin in _ORGANIZATION_ALIASES.items()
    ]
    for source, target in substitutions:
        if text.startswith(source):
            variants.add(target + text[len(source):])
    return sorted(variants)

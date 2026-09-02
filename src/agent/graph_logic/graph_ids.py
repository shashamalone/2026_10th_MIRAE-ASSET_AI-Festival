"""
GraphDB 엔티티 해소에 쓰는 식별자 정규화. 팀원의 gragh-test 노트북
`kb/ids.py`(셀 29)를 그대로 옮겼다 - 로직 변경 없음, 파일 위치만 우리
`sql_gen_test/` 평면 구조에 맞게 `kb.ids` 패키지 대신 단일 모듈로 뒀다.
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

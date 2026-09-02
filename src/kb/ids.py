# -*- coding: utf-8 -*-
"""지식그래프 엔티티 해소에 쓰는 식별자 정규화 단일 구현."""
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


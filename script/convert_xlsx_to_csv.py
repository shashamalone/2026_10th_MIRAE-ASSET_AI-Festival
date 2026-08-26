"""폐기된 2026-07-11 XLSX→CSV 변환 진입점.

공식 2026-08-24 XLSX는 읽기 전용으로 직접 검증·적재하며 운영 CSV 변환본을 만들지
않는다. 이 파일은 과거 자동화가 legacy CSV를 다시 만들지 못하게 명시적으로 실패한다.
"""
from __future__ import annotations


def main() -> None:
    raise SystemExit(
        "운영 XLSX→CSV 변환은 금지되었습니다. "
        "`python -m kb.build_data_platform_v2 --check` 또는 "
        "`python -m kb.build_data_platform_v2`를 사용하세요."
    )


if __name__ == "__main__":
    main()

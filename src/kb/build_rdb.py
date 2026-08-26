# -*- coding: utf-8 -*-
"""2026-07-11 CSV 빌더의 폐기된 호환 진입점.

운영 적재는 공식 2026-08-24 XLSX 8개만 허용한다. 과거 호출자가 조용히 legacy
CSV를 재적재하지 않도록 이 모듈은 항상 명시적으로 거부하고 V2 명령을 안내한다.
"""
from __future__ import annotations

import argparse


V2_COMMAND = "python -m kb.build_data_platform_v2"


def rejection_message() -> str:
    return (
        "legacy 2026-07-11 CSV 적재는 운영 계약에서 금지되었습니다. "
        "DATASET_DIR을 공식 ai-festival2026_금융상품Agent_DtataSet260824 XLSX 8개 "
        f"디렉터리로 지정한 뒤 `{V2_COMMAND}`를 실행하세요."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="폐기된 legacy RDB 빌더(공식 2026-08-24 V2 안내 전용)"
    )
    parser.add_argument("--check", action="store_true", help="호환 인자; 적재/검증 모두 거부")
    parser.parse_args()
    parser.error(rejection_message())


if __name__ == "__main__":
    main()

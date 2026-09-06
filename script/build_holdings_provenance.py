"""
ETF 편입내역 문서 출처 인덱스 생성기.

수집 당시 각 편입내역 JSON 옆에 남긴 사이드카(`*.meta.json`)에서 문서명·URL·
기준일·조회일시를 뽑아 `metadata/etf_holdings_provenance.json` 으로 굳힌다.

[왜 별도 인덱스인가]
골드셋 22번이 "편입내역 **문서명과 근거 문장**"을 요구하는데, 그래프의
`fp:sourceId` 에는 운용사 브랜드명("KODEX")밖에 없다. 문서명·URL 은 사이드카에만
있고, 배포된 Oxigraph 는 읽기 전용(`/update` 403)이라 트리플을 새로 넣을 수 없다.
그래서 답변 조립 시점에 조인할 수 있도록 작은 인덱스로 뽑아 둔다.

원천인 `data/` 는 `.gitignore` 대상이라 clone 하면 사라진다. 이 인덱스는
`metadata/` 에 커밋해서 재현 가능하게 만든다.

[cutoff]
`as_of` 가 2026-08-24 를 넘는 항목은 넣지 않는다. 데이터 규칙상 기준일 이후
외부값은 쓸 수 없다.

실행:
    python script/build_holdings_provenance.py
    python script/build_holdings_provenance.py --check   # 재생성 없이 차이만 보고
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import sys
from pathlib import Path

CUTOFF = "2026-08-24"
REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
SIDECAR_GLOB = str(
    WORKSPACE_ROOT / "data" / "data" / "external" / "etf_kr_holdings" / "*.meta.json"
)
OUT_PATH = REPO_ROOT / "metadata" / "etf_holdings_provenance.json"


def _identity(meta: dict) -> dict:
    """사이드카가 두 형태로 존재한다. 초기 ACE 수집분은 식별자를
    `identifier` 아래 중첩해 뒀고, 이후 수집분은 최상위에 평면으로 뒀다."""
    nested = meta.get("identifier") or {}
    return {
        "ticker": str(nested.get("ticker") or meta.get("ticker") or "").strip(),
        "isin": str(nested.get("isin") or meta.get("isin") or "").strip(),
        "name": str(nested.get("name") or meta.get("name") or "").strip(),
    }


def collect(pattern: str = SIDECAR_GLOB) -> tuple[dict, list[dict]]:
    entries: dict[str, dict] = {}
    skipped: list[dict] = []

    for path in sorted(glob.glob(pattern)):
        base = os.path.basename(path)
        try:
            meta = json.load(io.open(path, encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - 깨진 사이드카는 건너뛰고 기록만
            skipped.append({"file": base, "reason": f"parse_error: {type(exc).__name__}"})
            continue

        as_of = str(meta.get("as_of") or "")[:10]
        if not as_of:
            skipped.append({"file": base, "reason": "no_as_of"})
            continue
        if as_of > CUTOFF:
            skipped.append({"file": base, "reason": f"after_cutoff: {as_of}"})
            continue

        ident = _identity(meta)
        if not ident["ticker"]:
            # 식별자가 아예 없는 사이드카가 소수 있다(초기 KODEX 수집분).
            # 티커 없이는 편입 행과 맞출 수 없으므로 제외하되 기록은 남긴다.
            skipped.append({"file": base, "reason": "no_ticker", "url": meta.get("url", "")})
            continue

        entry = {
            "ticker": ident["ticker"],
            "isin": ident["isin"],
            "name": ident["name"],
            "document": str(meta.get("source") or "").strip(),
            "url": str(meta.get("url") or "").strip(),
            "as_of": as_of,
            "retrieved_at": str(meta.get("retrieved_at") or "").strip(),
            "holdings_count": meta.get("holdings_count"),
        }
        # 수집 근거로 남아 있으면 함께 보존한다. 자동 수집 허용 여부와
        # 원문 해시는 나중에 출처를 다툴 때 필요한 값이다.
        for optional in ("robots_txt", "sha256", "source_type"):
            if meta.get(optional):
                entry[optional] = meta[optional]

        entries[ident["ticker"]] = entry

    return dict(sorted(entries.items())), skipped


def build_payload(entries: dict, skipped: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "description": (
            "ETF 편입내역 문서 출처. 수집 사이드카(*.meta.json)에서 추출한다. "
            "재생성: python script/build_holdings_provenance.py"
        ),
        "cutoff": CUTOFF,
        "count": len(entries),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "entries": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ETF 편입내역 출처 인덱스 생성")
    parser.add_argument("--check", action="store_true", help="쓰지 않고 차이만 보고한다")
    args = parser.parse_args(argv)

    entries, skipped = collect()
    if not entries:
        print(f"사이드카를 찾지 못했다: {SIDECAR_GLOB}", file=sys.stderr)
        return 1

    payload = build_payload(entries, skipped)
    text = json.dumps(payload, ensure_ascii=False, indent=1) + "\n"

    if args.check:
        current = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else ""
        status = "동일" if current == text else "차이 있음"
        print(f"[check] {status} — 수록 {len(entries)}건 / 제외 {len(skipped)}건")
        return 0 if current == text else 2

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(text, encoding="utf-8")
    print(f"수록 {len(entries)}건 / 제외 {len(skipped)}건 -> {OUT_PATH.relative_to(REPO_ROOT)}")
    for item in skipped[:5]:
        print(f"  제외: {item['file']} ({item['reason']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

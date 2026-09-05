"""
로컬 bge-m3 임베딩이 배포본과 같은 벡터를 내는지 검증한다.

[왜 필요한가]
배포된 `vec.chunk_embedding` 은 CHECK 제약으로 `embedding_model='bge-m3'`,
`embedding_dim=1024` 를 강제하고, `vec.vector_deploy_run` 은 한 발 더 나가
`model_id='BAAI/bge-m3'` 까지 못박는다. 즉 새로 만든 벡터가 기존 것과 **같은
공간**에 있지 않으면 검색 결과가 조용히 망가진다. 차원과 모델명이 같다는 것만으로는
증명이 안 된다 - 리비전이 다르면 값이 달라지기 때문이다.

배포 번들(`chunk_embeddings.jsonl`)은 각 레코드에 `embedding_text` 와 그때 만든
`embedding` 을 **함께** 담고 있다. 그래서 같은 텍스트를 로컬에서 다시 임베딩해
코사인 유사도를 재면 등가성을 직접 증명할 수 있다.

[판정]
정규화된 벡터끼리의 코사인이 1.0 에 충분히 가까워야 한다. 부동소수점 누적과
배치 크기 차이로 완전한 1.0 은 나오지 않으므로 기본 임계는 0.9990 이다.

실행:
    python test/local-embedding/verify_local_embeddings.py --embeddings <bundle>/chunk_embeddings.jsonl
    python test/local-embedding/verify_local_embeddings.py --embeddings ... --sample 32 --json out.json
"""
from __future__ import annotations

import argparse
import io
import json
import math
import random
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

DEFAULT_THRESHOLD = 0.9990
DEFAULT_SAMPLE = 16


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"차원 불일치: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        raise ValueError("영벡터는 비교할 수 없음")
    return dot / (na * nb)


def load_samples(path: Path, sample: int, seed: int) -> list[dict]:
    """`embedding_text` 와 `embedding` 을 모두 가진 레코드만 고른다."""
    records: list[dict] = []
    with io.open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("embedding_text") and item.get("embedding"):
                records.append(item)

    if not records:
        raise SystemExit(f"검증 가능한 레코드가 없다: {path}")

    random.Random(seed).shuffle(records)
    return records[:sample]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="로컬 bge-m3 임베딩 등가성 검증")
    parser.add_argument("--embeddings", required=True, type=Path,
                        help="배포 번들의 chunk_embeddings.jsonl 경로")
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE)
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--json", type=Path, help="결과를 JSON 으로 저장")
    args = parser.parse_args(argv)

    if not args.embeddings.exists():
        print(f"번들을 찾을 수 없다: {args.embeddings}", file=sys.stderr)
        return 2

    from kb.local_embeddings import MODEL_ID, MODEL_REVISION, BgeM3Embedder  # noqa: PLC0415

    samples = load_samples(args.embeddings, args.sample, args.seed)
    print(f"표본 {len(samples)}건 / 모델 {MODEL_ID}@{MODEL_REVISION[:8]}")

    # 배포 당시 기록된 모델 메타가 우리가 쓰려는 것과 같은지 먼저 본다.
    meta_mismatch = [
        {
            "content_hash": s.get("content_hash"),
            "embedding_model": s.get("embedding_model"),
            "model_revision": s.get("model_revision"),
        }
        for s in samples
        if s.get("model_revision") not in (None, MODEL_REVISION)
    ]
    if meta_mismatch:
        print(f"경고: 번들의 model_revision 이 다르다 ({len(meta_mismatch)}건)", file=sys.stderr)

    embedder = BgeM3Embedder(show_progress=False)
    vectors = embedder.encode([s["embedding_text"] for s in samples])

    scores: list[float] = []
    worst: dict | None = None
    for sample, local in zip(samples, vectors):
        score = cosine(sample["embedding"], local)
        scores.append(score)
        if worst is None or score < worst["cosine"]:
            worst = {
                "cosine": score,
                "content_hash": sample.get("content_hash"),
                "text_head": str(sample["embedding_text"])[:80],
            }

    lowest, highest = min(scores), max(scores)
    mean = sum(scores) / len(scores)
    passed = lowest >= args.threshold

    print(f"코사인  최저 {lowest:.6f} / 평균 {mean:.6f} / 최고 {highest:.6f}")
    print(f"임계 {args.threshold} → {'PASS' if passed else 'FAIL'}")
    if worst and not passed:
        print(f"  최저 표본: {worst['content_hash']}\n  {worst['text_head']}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(
                {
                    "model_id": MODEL_ID,
                    "model_revision": MODEL_REVISION,
                    "sample_size": len(samples),
                    "threshold": args.threshold,
                    "cosine_min": lowest,
                    "cosine_mean": mean,
                    "cosine_max": highest,
                    "passed": passed,
                    "metadata_mismatch": meta_mismatch,
                    "worst": worst,
                },
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"결과 저장: {args.json}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

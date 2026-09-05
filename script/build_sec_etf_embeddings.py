"""
선별된 SEC 청크에 로컬 bge-m3 임베딩을 붙여 적재용 번들을 만든다.

[왜 로컬인가]
CLOVA 임베딩은 60 req/분 고정창에 걸려 수천 건이면 시간이 크게 늘고 비용이 든다.
로컬 bge-m3 는 같은 모델·같은 리비전을 쓰면 벡터가 동등하므로, 배포본과 같은
공간에 들어간다.

[리비전을 고정하는 이유]
`vec.chunk_embedding` 은 `embedding_model='bge-m3'`, `embedding_dim=1024` 만 CHECK 로
막고 **리비전은 강제하지 않는다**. 리비전이 다르면 값이 달라져 한글 DART 청크와
영문 SEC 청크가 다른 공간에 놓이고, 검색이 에러 없이 조용히 망가진다. 그래서
`kb.local_embeddings.MODEL_REVISION`(배포본과 동일)을 그대로 쓰고 결과에 기록한다.

출력은 배포 번들과 같은 `mirae-vector-bundle-v1` 형식이다. 실제 적재는 쓰기 권한이
있는 쪽에서 이 번들을 그대로 넣으면 된다.

실행:
    python script/build_sec_etf_embeddings.py --in artifacts/sec_etf_selected --batch 16
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

CUTOFF = "2026-08-24"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in io.open(path, encoding="utf-8") if line.strip()]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with io.open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SEC 청크 로컬 임베딩")
    parser.add_argument("--in", dest="src", required=True, type=Path)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--max-seq-length", type=int, default=1024,
                        help="기본 8192 는 낭비다. 실측 토큰 최대 392 라 1024 면 잘리지 않는다")
    parser.add_argument("--release-id", default="", help="선택. 번들 manifest 에 기록")
    args = parser.parse_args(argv)

    from kb.local_embeddings import (  # noqa: PLC0415
        DIMENSION, MODEL_ID, MODEL_LABEL, MODEL_REVISION, BgeM3Embedder,
    )

    chunks_path = args.src / "document_chunks.jsonl"
    chunks = read_jsonl(chunks_path)
    if not chunks:
        print(f"청크가 없다: {chunks_path}", file=sys.stderr)
        return 1

    # 같은 본문이 여러 청크에 나오면 임베딩은 한 번만 만든다.
    unique: dict[str, str] = {}
    for chunk in chunks:
        unique.setdefault(chunk["content_hash"], chunk["embedding_text"])
    hashes = list(unique)
    texts = [unique[h] for h in hashes]
    print(f"청크 {len(chunks):,} / 고유 본문 {len(texts):,}")
    print(f"모델 {MODEL_ID}@{MODEL_REVISION[:8]} dim={DIMENSION}")

    embedder = BgeM3Embedder(batch_size=args.batch, show_progress=False)
    encoder = embedder._load()
    if args.max_seq_length:
        encoder.max_seq_length = args.max_seq_length

    vectors: list[list[float]] = []
    started = time.time()
    for offset in range(0, len(texts), args.batch):
        batch = texts[offset: offset + args.batch]
        vectors.extend(embedder.encode(batch))
        done = len(vectors)
        elapsed = time.time() - started
        rate = done / elapsed if elapsed else 0
        remain = (len(texts) - done) / rate / 60 if rate else 0
        print(f"  {done:>6,}/{len(texts):,}  {rate:5.2f}/s  남은 {remain:5.1f}분", flush=True)

    out_dir = args.src
    emb_path = out_dir / "chunk_embeddings.jsonl"
    with io.open(emb_path, "w", encoding="utf-8") as fh:
        for content_hash, text, vector in zip(hashes, texts, vectors):
            fh.write(json.dumps({
                "content_hash": content_hash,
                "embedding_text": text,
                "embedding_model": MODEL_LABEL,
                "model_revision": MODEL_REVISION,
                "embedding_dim": DIMENSION,
                "embedding": vector,
            }, ensure_ascii=False) + "\n")

    names = ["source_documents.jsonl", "product_documents.jsonl",
             "document_chunks.jsonl", "chunk_embeddings.jsonl"]
    present = [n for n in names if (out_dir / n).exists()]
    manifest = {
        "format_version": "mirae-vector-bundle-v1",
        "generator": "script/build_sec_etf_embeddings.py",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cutoff": CUTOFF,
        "source": "SEC DERA Mutual Fund Prospectus Risk/Return Summary Data Sets",
        "model_id": MODEL_ID,
        "model_label": MODEL_LABEL,
        "model_revision": MODEL_REVISION,
        "embedding_dim": DIMENSION,
        "normalized": True,
        "distance": "cosine",
        "max_seq_length": args.max_seq_length,
        "release_id": args.release_id,
        "counts": {n: sum(1 for _ in io.open(out_dir / n, encoding="utf-8")) for n in present},
        "bytes": {n: (out_dir / n).stat().st_size for n in present},
        "sha256": {n: file_sha256(out_dir / n) for n in present},
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    total = time.time() - started
    print(f"\n완료 {len(vectors):,}벡터 / {total/60:.1f}분")
    print(f"번들: {out_dir}")
    for name, count in manifest["counts"].items():
        print(f"  {name}: {count:,}행")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

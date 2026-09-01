#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전체 TBox class 임베딩 인덱스를 artifacts에 구축한다."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import clova  # noqa: E402
from config import EMBEDDING_MODEL  # noqa: E402
from tools.graph_schema import SCHEMA_INDEX_PATH, catalog  # noqa: E402


def build() -> dict:
    schema = catalog()
    classes = schema.class_resources()
    texts = [f"{x['label']}\n{x['comment']}" for x in classes]
    vectors = clova.embed_many(texts)
    payload = {
        "version": 1,
        "model": EMBEDDING_MODEL,
        "tbox_fingerprint": schema.fingerprint(),
        "classes": [{**row, "embedding": vector} for row, vector in zip(classes, vectors)],
    }
    SCHEMA_INDEX_PATH.parent.mkdir(exist_ok=True)
    SCHEMA_INDEX_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return {"classes": len(classes), "dimension": len(vectors[0]) if vectors else 0,
            "path": str(SCHEMA_INDEX_PATH)}


def check() -> dict:
    if not SCHEMA_INDEX_PATH.is_file():
        raise ValueError(f"Graph schema index가 없습니다: {SCHEMA_INDEX_PATH}")
    payload = json.loads(SCHEMA_INDEX_PATH.read_text(encoding="utf-8"))
    schema = catalog()
    if payload.get("tbox_fingerprint") != schema.fingerprint():
        raise ValueError("TBox 변경 후 Graph schema index를 재생성하지 않았습니다")
    classes = payload.get("classes") or []
    dimensions = {len(x.get("embedding") or []) for x in classes}
    if len(classes) != len(schema.classes) or dimensions != {1024}:
        raise ValueError(f"Graph schema index shape 오류: classes={len(classes)}, dim={dimensions}")
    return {"classes": len(classes), "dimension": 1024, "path": str(SCHEMA_INDEX_PATH)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = check() if args.check else build()
    print("PASS " + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()


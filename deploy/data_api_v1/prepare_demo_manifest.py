# -*- coding: utf-8 -*-
"""Fill source/chunk SHA-256 values in a two-document demo manifest template."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("template", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    template = args.template.resolve()
    output = args.output.resolve()
    if output.exists() and not args.force:
        raise SystemExit(f"REFUSE_EXISTING: {output}; use --force only after inspecting it")
    payload = json.loads(template.read_text(encoding="utf-8"))
    for item in payload.get("documents", []):
        source = (template.parent / item["source_file"]).resolve()
        extracted = (template.parent / item["extracted_text_file"]).resolve()
        if not source.is_file() or not extracted.is_file():
            raise SystemExit(f"MISSING_SOURCE: source={source} extracted={extracted}")
        item["source_sha256"] = digest(source)
        item["extracted_text_sha256"] = digest(extracted)
        item["chunk_sha256"] = hashlib.sha256(item["chunk_text"].encode("utf-8")).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"MANIFEST PASS: {output}")


if __name__ == "__main__":
    main()

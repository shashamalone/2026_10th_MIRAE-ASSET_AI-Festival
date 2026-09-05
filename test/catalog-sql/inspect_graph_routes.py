"""Read-only Graph route diagnostics with a forbidden model generator."""
import argparse
import contextlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if (ROOT / "artifacts/runs").resolve() not in out.parents or "codex-t139-sql-0905" not in out.parts:
        parser.error("agent-scoped output required")
    out.mkdir(parents=True, exist_ok=True)
    from dotenv import load_dotenv
    load_dotenv(args.env_file)
    from agent.graph_logic import graph_orchestrator

    def forbidden(*args):
        raise RuntimeError("LLM deliberately disabled for diagnostic; missing deterministic route")

    cases = [("cambricon", "캠브리콘", "company", False),
             ("ecopro", "에코프로", "company", True),
             ("hynix", "SK하이닉스", "company", False),
             ("nvidia", "엔비디아", "company", False),
             ("lgenergy", "LG에너지솔루션", "company", True)]
    summary = []
    for label, name, role, subsidiaries in cases:
        relations = ([{"id": "r1", "relation": "subsidiary_of", "subject_domain": "company", "object_entity": name}] if subsidiaries else [])
        relations.append({"id": "r2", "relation": "holds", "subject_domain": "국내ETF", "object_entity": "" if subsidiaries else name, "object_ref": "r1" if subsidiaries else ""})
        frame = {"entities": [{"text": name, "role": role}], "relations": relations, "relation_scope": True, "limit": 100}
        with (out / f"{label}.log").open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log):
            result = graph_orchestrator.run("explicit relation frame only", frame, generator=forbidden, max_corrections=1)
        (out / f"{label}.json").write_text(json.dumps({"frame": frame, "result": result, "paid_calls": 0}, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
        summary.append({"name": label, "status": result["status"], "rows": len(result.get("rows") or []), "products": len(result.get("entity_codes") or []), "trace": result.get("trace")})
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()

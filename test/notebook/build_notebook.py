# -*- coding: utf-8 -*-
"""src/*.py 전체를 하나의 ipynb로 묶는 생성기. 재실행하면 src 최신본으로 재생성된다."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
OUT = Path(__file__).parent / "src_all_in_one.ipynb"

# (모듈명, src 기준 상대경로) — 의존성 순서
FILES = [
    ("config", "config.py"),
    ("clova", "clova.py"),
    ("agent.state", "agent/state.py"),
    ("agent.prompt", "agent/prompt.py"),
    ("agent.query_frame", "agent/query_frame.py"),
    ("tools.schema_context", "tools/schema_context.py"),
    ("tools.validate", "tools/validate.py"),
    ("tools.route", "tools/route.py"),
    ("tools.rdb", "tools/rdb.py"),
    ("tools.graph", "tools/graph.py"),
    ("tools.content", "tools/content.py"),
    ("tools.bond_schema", "tools/bond_schema.py"),
    ("agent.nodes", "agent/nodes.py"),
    ("agent.agent_core", "agent/agent_core.py"),
    ("kb.build_rdb", "kb/build_rdb.py"),
    ("kb.build_graph", "kb/build_graph.py"),
    ("kb.build_schema_catalog", "kb/build_schema_catalog.py"),
    ("kb.build_bond_index", "kb/build_bond_index.py"),
    ("kb.build_content_index", "kb/build_content_index.py"),
]

SETUP = '''\
# === 셀 매직 정의: 각 셀을 실제 모듈로 등록한다 ===
# 사용법: 셀 첫 줄에 `%%module <모듈명> <src 기준 경로>`.
# 셀을 수정하고 재실행하면 sys.modules 가 교체되므로,
# 그 모듈을 import 하는 하위 셀들을 다시 실행하면 수정본이 반영된다.
import json as _json
import sys as _sys
import types as _types
from pathlib import Path

from IPython.core.magic import register_cell_magic

REPO_ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "src").is_dir())
NB_PATH = REPO_ROOT / "test" / "notebook" / "src_all_in_one.ipynb"


@register_cell_magic("module")
def _module_magic(line, cell):
    name, relpath = line.split()
    mod = _types.ModuleType(name)
    mod.__file__ = str(REPO_ROOT / "src" / relpath)
    _sys.modules[name] = mod
    # 부모 패키지 등록 (agent.nodes -> agent)
    parts = name.split(".")
    for i in range(1, len(parts)):
        pkg = ".".join(parts[:i])
        parent = _sys.modules.setdefault(pkg, _types.ModuleType(pkg))
        setattr(parent, parts[i], _sys.modules.get(name) if i == len(parts) - 1 else _sys.modules.setdefault(".".join(parts[:i + 1]), _types.ModuleType(".".join(parts[:i + 1]))))
    exec(compile(cell, mod.__file__, "exec"), mod.__dict__)
    print(f"registered: {name}")


def sync_to_py(dry_run=True):
    """노트북의 %%module 셀들을 src/*.py 로 되쓴다. 먼저 노트북을 저장(Ctrl+S)할 것.

    dry_run=True 면 diff 여부만 보여준다. 실제 반영은 sync_to_py(dry_run=False).
    """
    nb = _json.loads(NB_PATH.read_text(encoding="utf-8"))
    for c in nb["cells"]:
        src = "".join(c["source"])
        if c["cell_type"] != "code" or not src.startswith("%%module "):
            continue
        first, _, body = src.partition("\\n")
        _, name, relpath = first.split()
        target = REPO_ROOT / "src" / relpath
        old = target.read_text(encoding="utf-8")
        if old == body:
            print(f"  same: {relpath}")
        elif dry_run:
            print(f"CHANGED: {relpath}  (dry_run — 반영하려면 sync_to_py(dry_run=False))")
        else:
            target.write_text(body, encoding="utf-8")
            print(f"WROTE: {relpath}")
'''

TEST_CELLS = [
    ("md", "# 노드별 테스트\n\n"
           "아래는 LangGraph 를 거치지 않고 노드 함수를 하나씩 실행하는 셀이다.\n"
           "위의 모듈 셀을 수정했다면 해당 셀 → `agent.nodes` 셀 → 여기 순서로 재실행한다.\n\n"
           "그래프 흐름: extract_query_frame → ground_query → validate_query →(abstain 이면 render_answer)→ "
           "select_route →(rdb_only 아니면 render_answer)→ execute_rdb → verify_results → render_answer"),
    ("code", 'from agent import nodes as N\n\n'
             'TEST_QUESTION = "여기에 테스트 질문"  # 예: expected_qa 의 채권 문항\n\n'
             'state = {"question_id": "test", "question": TEST_QUESTION, "intent": {},\n'
             '         "metadata_context": {}, "plan": {}, "route": {}, "results": {}, "evidence": [],\n'
             '         "abstain": None, "trace": [], "answer": ""}'),
    ("code", 'out = N.extract_query_frame(state); state.update(out); out'),
    ("code", 'out = N.ground_query(state); state.update(out); out'),
    ("code", 'out = N.validate_query(state); state.update(out); out\n'
             '# state["abstain"] 이 있으면 이후는 render_answer 로 직행하는 경로다'),
    ("code", 'out = N.select_route(state); state.update(out); out'),
    ("code", 'out = N.execute_rdb(state); state.update(out); out'),
    ("code", 'out = N.verify_results(state); state.update(out); out'),
    ("code", 'out = N.render_answer(state); state.update(out)\nprint(state["answer"])'),
    ("md", "## Agent 그래프 시각화"),
    ("code", 'from IPython.display import Markdown, display\n'
             'from agent.agent_core import APP\n\n'
             '# 컴파일된 LangGraph에서 Mermaid 정의를 생성한다.\n'
             'agent_graph = APP.get_graph()\n'
             'mermaid = agent_graph.draw_mermaid()\n\n'
             '# Jupyter 환경에 따라 Mermaid 정의를 Markdown으로 표시한다.\n'
             'display(Markdown("### Mermaid graph definition\\n\\n" + mermaid))\n\n'
             '# Mermaid가 렌더링되지 않는 환경을 위한 텍스트 흐름도.\n'
             'print("START -> extract_query_frame -> ground_query -> validate_query")\n'
             'print("validate_query -- abstain 있음 --> render_answer -> END")\n'
             'print("validate_query -- 정상 --> select_route")\n'
             'print("select_route -- rdb_only --> execute_rdb -> verify_results -> render_answer -> END")\n'
             'print("select_route -- 그 외 --> render_answer -> END")'),
    ("md", "## 전체 그래프 E2E"),
    ("code", 'from agent.agent_core import ask\n\nresp = ask(TEST_QUESTION)\nresp'),
    ("md", "## .py 반영\n\n셀 수정 후 **노트북 저장(Ctrl+S)** → 아래 실행."),
    ("code", '# sync_to_py()                # diff 확인\n# sync_to_py(dry_run=False)   # 실제 반영'),
]


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.splitlines(keepends=True)}


cells = [
    md("# src 통합 노트북\n\n"
       "`src/*.py` 전체를 의존성 순서대로 한 노트북에 담았다. 각 코드 셀은 파일 내용 **verbatim** 이며,\n"
       "`%%module` 매직이 셀을 실제 파이썬 모듈로 등록하므로 파일 간 import 가 그대로 동작한다.\n\n"
       "**워크플로**: ① 전체 셀 실행 → ② 수정할 모듈 셀 편집·재실행 → ③ 그 모듈을 쓰는 하위 셀 재실행 →\n"
       "④ 맨 아래 노드별 테스트 → ⑤ 저장 후 `sync_to_py(dry_run=False)` 로 .py 반영.\n\n"
       "재생성: `python test/notebook/build_notebook.py` (src 최신본 기준으로 덮어씀 — 노트북에서 수정 중이면 먼저 sync 할 것)"),
    code(SETUP),
]
for name, rel in FILES:
    body = (SRC / rel).read_text(encoding="utf-8")
    cells.append(md(f"## `src/{rel}`"))
    cells.append(code(f"%%module {name} {rel}\n" + body))
for kind, text in TEST_CELLS:
    cells.append(md(text) if kind == "md" else code(text))

nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                   "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 5}
OUT.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"wrote {OUT} ({len(cells)} cells)")

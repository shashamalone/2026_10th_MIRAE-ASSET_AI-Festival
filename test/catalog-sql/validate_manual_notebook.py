"""Offline real-kernel notebook QA; uses existing nbformat/nbclient, installs nothing.

Run with an environment already containing nbformat and nbclient. --python is
the actual notebook kernel executable (mirae-agent Python 3.13 in this workspace).
The delivered notebook stays unexecuted. Executed QA copies are run artifacts.
"""
import argparse
import json
from pathlib import Path
import tempfile

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager


ROOT = Path(__file__).resolve().parents[2]
AGENT_ID = "codex-t139-sql-0905"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    output_dir = args.out.resolve()
    if not output_dir.is_relative_to(ROOT / "artifacts/runs") or output_dir.name != AGENT_ID:
        parser.error("--out must be this worktree's artifacts/runs/<run-id>/" + AGENT_ID)
    if not args.python.is_file():
        parser.error("--python must be an existing interpreter; no install is performed")
    output_dir.mkdir(parents=True, exist_ok=False)
    notebook = nbformat.read(ROOT / "test/catalog-sql/manual_query_debug.ipynb", as_version=4)
    nbformat.validate(notebook)
    # Guard the offline QA process, including against accidental future changes.
    # This notebook copy is not the delivered editable source.
    guard = nbformat.v4.new_code_cell(
        "import socket\n"
        "def _forbid_network(*args, **kwargs):\n"
        "    raise AssertionError('Offline notebook QA: network forbidden')\n"
        "socket.create_connection = _forbid_network\n"
        "socket.socket.connect = _forbid_network\n"
        "socket.socket.connect_ex = _forbid_network\n"
    )
    notebook.cells.insert(0, guard)
    notebook.cells.append(nbformat.v4.new_code_cell(
        "assert RUN_LIVE is False\nassert REPORT is None\n"
        "assert 'agent.graph' not in sys.modules\n"
        "print('OFFLINE QA: all cells executed; no graph/model imported; no external network')\n"
    ))
    with tempfile.TemporaryDirectory(prefix="notebook-kernel-", dir=output_dir) as directory:
        kernels_dir = Path(directory)
        kernel_dir = kernels_dir / "mirae-offline-qa"
        kernel_dir.mkdir()
        (kernel_dir / "kernel.json").write_text(json.dumps({
            "argv": [str(args.python.resolve()), "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            "display_name": "mirae offline QA", "language": "python",
            "env": {"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        }), encoding="utf-8")
        spec_manager = KernelSpecManager(kernel_dirs=[str(kernels_dir)], ensure_native_kernel=False)
        manager = KernelManager(kernel_name="mirae-offline-qa", kernel_spec_manager=spec_manager)
        client = NotebookClient(notebook, km=manager, timeout=90,
                                resources={"metadata": {"path": str(ROOT)}})
        try:
            client.execute()
        finally:
            if manager.has_kernel:
                manager.shutdown_kernel(now=True)
    nbformat.validate(notebook)
    nbformat.write(notebook, output_dir / "manual_query_debug.executed.ipynb")
    summary = {"status": "passed", "python": str(args.python.resolve()),
               "source_cells": len(notebook.cells) - 2,
               "code_cells_executed": sum(c.cell_type == "code" for c in notebook.cells),
               "external_network": "blocked", "paid_calls": 0}
    (output_dir / "validation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

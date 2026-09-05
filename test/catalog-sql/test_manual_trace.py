"""No database/model calls. Verify notebook observation using small fake graphs."""
import io
import ast
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import manual_trace as trace


class ManualTraceTests(unittest.TestCase):
    def graph(self, *, fail=False):
        from langgraph.graph import END, StateGraph
        from typing import Annotated, TypedDict
        import operator

        class State(TypedDict, total=False):
            question: str
            question_id: str
            max_sql_retries: int
            intent: dict
            step_results: dict
            answer: str
            trace: Annotated[list, operator.add]

        graph = StateGraph(State)
        graph.add_node("analyze_intent", lambda s: {"intent": {"task": "lookup"}, "trace": ["analysis"]})

        def retrieve(s):
            if fail:
                raise RuntimeError("offline failure")
            return {"step_results": {"r1": {"engine": "rdb", "sql": "SELECT 1 AS value", "rows": [{"value": 1}]}}}

        graph.add_node("rdb_search", retrieve)
        graph.add_node("generate_answer", lambda s: {"answer": json.dumps({"answer": "OFFLINE FIXTURE", "question": s["question"]})})
        graph.set_entry_point("analyze_intent")
        graph.add_edge("analyze_intent", "rdb_search")
        graph.add_edge("rdb_search", "generate_answer")
        graph.add_edge("generate_answer", END)
        return graph.compile()

    def test_real_langgraph_callbacks_and_updates_preserve_node_io(self):
        recorder = trace.Recorder(trace.Redactor())
        events = io.StringIO()
        report = trace.collect_stream(self.graph(), {"question": "offline", "question_id": "demo"}, recorder, events_file=events)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["answer"]["answer"], "OFFLINE FIXTURE")
        self.assertEqual(report["step_results"]["r1"]["rows"], [{"value": 1}])
        self.assertEqual(report["initial_intent"], {"task": "lookup"})
        self.assertEqual([r["node"] for r in report["node_runs"]], ["analyze_intent", "rdb_search", "generate_answer"])
        self.assertIn("question", report["node_runs"][0]["input"])
        self.assertTrue(all("output" in r and "duration_s" in r for r in report["node_runs"]))
        self.assertEqual(len(events.getvalue().splitlines()), 3)

    def test_failure_retains_previous_intent_and_error_node(self):
        report = trace.collect_stream(self.graph(fail=True), {"question": "offline", "question_id": "demo"}, trace.Recorder(trace.Redactor()))
        self.assertEqual(report["status"], "error")
        self.assertIn("offline failure", report["exception"])
        self.assertEqual(report["initial_intent"], {"task": "lookup"})
        self.assertIsNone(report["answer"])
        self.assertEqual(report["node_runs"][-1]["status"], "error")

    def test_view_callback_failure_does_not_restart_or_stop_graph(self):
        report = trace.collect_stream(self.graph(), {"question": "offline", "question_id": "demo"}, trace.Recorder(trace.Redactor()),
                                      on_event=Mock(side_effect=RuntimeError("display broken")))
        self.assertEqual(report["status"], "completed")
        self.assertEqual(len(report["viewer_warnings"]), 3)

    def test_redaction_masks_keys_strings_and_split_console_writes(self):
        with patch.dict(os.environ, {"CLOVASTUDIO_API_KEY": "test-secret-abcdef"}):
            redactor = trace.Redactor()
        cleaned = redactor.clean({"api_key": "private", "text": "Bearer token-value test-secret-abcdef", "pd_no": "KR123"})
        self.assertEqual(cleaned["pd_no"], "KR123")
        self.assertNotIn("token-value", trace.json_text(cleaned))
        self.assertNotIn("test-secret", trace.json_text(cleaned))
        stream = io.StringIO()
        writer = trace._LogWriter(stream, redactor)
        writer.write("Bearer test-secret-")
        writer.write("abcdef\n")
        self.assertNotIn("abcdef", stream.getvalue())
        stream.close()
        writer.close()  # closing the owning file first must not trigger an ignored destructor error

    def test_query_wrapper_keeps_statement_rows_error_and_arguments(self):
        recorder = trace.Recorder(trace.Redactor())
        original = Mock(return_value=[{"x": None}, {"x": 0}])

        def query(sql, params=None):
            return original(sql, params)

        observed = recorder.wrapper(query, "sql", lambda a: {"sql": a["sql"], "params": a["params"]})
        self.assertEqual(observed("SELECT %s", [0]), [{"x": None}, {"x": 0}])
        original.assert_called_once_with("SELECT %s", [0])
        self.assertEqual(recorder.calls[0]["returned_rows"], 2)
        original.side_effect = RuntimeError("db unavailable")
        with self.assertRaises(RuntimeError):
            observed("SELECT 2")
        self.assertEqual(recorder.calls[-1]["status"], "error")

    def test_instrument_restores_originals_after_failure_without_querying(self):
        with patch.dict(os.environ, {"CLOVASTUDIO_API_KEY": "offline-test-key"}):
            from agent import utils, nodes
            from tools import schema_snapshot
            from agent.graph_logic import graph_engine
        original = (utils.run_sql, nodes.embed, graph_engine.sparql, schema_snapshot.DEFAULT_SNAPSHOT_PATH, nodes._MAX_RATE_LIMIT_WAITS)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "fixture"):
                with trace.instrument(trace.Recorder(trace.Redactor()), Path(directory) / "snapshot.json"):
                    self.assertIsNot(utils.run_sql, original[0])
                    self.assertEqual(nodes._MAX_RATE_LIMIT_WAITS, 0)
                    raise RuntimeError("fixture")
        self.assertEqual((utils.run_sql, nodes.embed, graph_engine.sparql, schema_snapshot.DEFAULT_SNAPSHOT_PATH, nodes._MAX_RATE_LIMIT_WAITS), original)

    def test_artifacts_roundtrip_and_legacy_reader_are_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            report = trace.collect_stream(self.graph(), {"question": "offline", "question_id": "demo"}, trace.Recorder(trace.Redactor()))
            report["manifest"] = {"commit": "offline"}
            report["calls"] = [{"call_id": 1, "sql": "SELECT 1"}]
            trace._save_report(report, path)
            loaded = trace.load_report(path)
            self.assertEqual(loaded["answer"]["answer"], "OFFLINE FIXTURE")
            self.assertEqual((path / "queries/001.sql").read_text(encoding="utf-8"), "SELECT 1")
            legacy = path / "old.jsonl"
            legacy.write_text(json.dumps({"intent": {"task": "lookup"}, "e2e_ms": 500, "trace_messages": ["old"], "answer": {"answer": "old"}}), encoding="utf-8")
            old = trace.load_report(legacy)
            self.assertEqual(old["elapsed_s"], 0.5)
            self.assertEqual(old["final_state"]["trace"], ["old"])

    def test_blank_and_repeat_guards_before_api_import(self):
        with self.assertRaises(ValueError):
            trace.run_question(" ", env_file="absent")
        signature = trace.hashlib.sha256(b"source\noffline").hexdigest()
        with patch.object(trace, "_source_manifest", return_value={"source_fingerprint": "source"}), \
             patch.object(trace, "_ATTEMPTED", {signature}), patch.object(trace, "_LOADED_SOURCE_HASH", None):
            with self.assertRaisesRegex(RuntimeError, "이미 시도"):
                trace.run_question("offline", env_file="absent")
        self.assertFalse(trace._RUN_LOCK.locked())

    def test_notebook_is_clean_valid_python_and_offline_guard_prevents_paid_execution(self):
        notebook = json.loads((Path(__file__).with_name("manual_query_debug.ipynb")).read_text(encoding="utf-8"))
        self.assertEqual(notebook["nbformat"], 4)
        self.assertEqual(sum(cell["cell_type"] == "code" for cell in notebook["cells"]), 2)
        self.assertEqual(sum("trace.run_question(" in "".join(cell["source"])
                             for cell in notebook["cells"]), 1)
        namespace = {"__name__": "__notebook_test__"}
        with patch.dict(os.environ, {"MIRAE_NOTEBOOK_OFFLINE_QA": "1"}), \
             patch.object(trace, "run_question", side_effect=AssertionError("live execution forbidden")) as live, \
             patch("IPython.display.display"), patch("sys.stdout", new_callable=io.StringIO):
            for cell in notebook["cells"]:
                if cell["cell_type"] != "code":
                    continue
                self.assertEqual(cell["outputs"], [])
                self.assertIsNone(cell["execution_count"])
                source = "".join(cell["source"])
                ast.parse(source)
                exec(compile(source, f"notebook:{cell['id']}", "exec"), namespace)
        live.assert_not_called()
        self.assertIs(namespace["RUN_LIVE"], False)
        self.assertIsNone(namespace["REPORT"])

    def test_all_notebook_viewers_render_saved_fixture_without_api(self):
        notebook = json.loads((Path(__file__).with_name("manual_query_debug.ipynb")).read_text(encoding="utf-8"))
        report = trace.collect_stream(self.graph(), {"question": "offline", "question_id": "demo"}, trace.Recorder(trace.Redactor()))
        report.update(plan=[{"step_id": "r1", "engine": "rdb", "depends_on": []}],
                      verified_intent={"task": "lookup", "verified": True},
                      calls=[{"call_id": 1, "sql": "SELECT %s", "params": [0], "result": [{"value": None}]}],
                      llm_calls=[{"node": "analyze_intent", "usage": {"input_tokens": 12}}])
        report["step_results"]["g1"] = {"engine": "graph", "sparql": "SELECT ?s WHERE {?s ?p ?o}",
                                         "rows": [{"label": "<script>unsafe</script>"}], "evidence": [{"source": "fixture"}]}
        report["step_results"]["v1"] = {"engine": "vector", "chunks": [{"chunk_text": "fixture text",
            "source_url": "https://example.invalid/fixture", "page_number": 1, "score": 0.8}]}
        namespace = {"__name__": "__notebook_test__", "REPORT": report}
        with patch.dict(os.environ, {"MIRAE_NOTEBOOK_OFFLINE_QA": "1"}), \
             patch.object(trace, "run_question", side_effect=AssertionError("live execution forbidden")) as live, \
             patch("IPython.display.display") as display, patch("sys.stdout", new_callable=io.StringIO):
            for cell in notebook["cells"]:
                if cell["cell_type"] == "code":
                    exec(compile("".join(cell["source"]), f"notebook:{cell['id']}", "exec"), namespace)
        live.assert_not_called()
        rendered_html = "\n".join(str(call.args[0].data) for call in display.call_args_list if type(call.args[0]).__name__ == "HTML")
        self.assertIn("&lt;script&gt;unsafe&lt;/script&gt;", rendered_html)
        self.assertNotIn("<script>unsafe</script>", rendered_html)
        self.assertIn("fixture text", rendered_html)
        self.assertIn("input_tokens", rendered_html)
        self.assertIs(namespace["REPORT"], report)

    def test_live_entrypoint_once_and_recoverable_artifacts_with_fake_app(self):
        with patch.dict(os.environ, {"CLOVASTUDIO_API_KEY": "offline-test-key"}):
            from agent import graph
        fake_app = Mock(wraps=self.graph())
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.touch()
            with patch.object(graph, "app", fake_app), \
                 patch.object(trace, "OUTPUT_ROOT", Path(directory) / "runs"), \
                 patch.object(trace, "_ATTEMPTED", set()), patch.object(trace, "_LOADED_SOURCE_HASH", None), \
                 patch.dict(os.environ, {"CLOVASTUDIO_API_KEY": "offline-test-key"}), \
                 patch("requests.Session.request", side_effect=AssertionError("network forbidden")), \
                 patch("psycopg2.connect", side_effect=AssertionError("DB forbidden")):
                report = trace.run_question("offline", env_file=env_file)
                fake_app.stream.assert_called_once()
                self.assertEqual(report["status"], "completed")
                run_dir = Path(report["run_dir"])
                for name in ("trace.json", "manifest.json", "calls.json", "events.jsonl", "run.log", "answer.md"):
                    self.assertTrue((run_dir / name).is_file(), name)
                self.assertEqual(trace.load_report(run_dir)["answer"]["answer"], "OFFLINE FIXTURE")
                with self.assertRaisesRegex(RuntimeError, "이미 시도"):
                    trace.run_question("offline", env_file=env_file)
                fake_app.stream.assert_called_once()
        self.assertFalse(trace._RUN_LOCK.locked())


if __name__ == "__main__":
    unittest.main()

import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ctx


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def init_memory(self):
        args = argparse.Namespace(path=str(self.root))
        self.assertEqual(ctx.cmd_memory_init(args), 0)

    def test_init_is_idempotent_and_preserves_content(self):
        self.init_memory()
        rules = self.root / "memory" / "project-rules.md"
        self.assertTrue((self.root / "memory" / ".gitignore").is_file())
        self.assertIn("node_modules/", (self.root / ".gitignore").read_text(encoding="utf-8"))
        rules.write_text("custom rules\n", encoding="utf-8")
        self.init_memory()
        self.assertEqual(rules.read_text(encoding="utf-8"), "custom rules\n")
        self.assertTrue((self.root / "memory" / "templates" / "bug.md").is_file())

    def test_check_detects_missing_broken_link_and_large_index(self):
        self.init_memory()
        (self.root / "memory" / "architecture.md").unlink()
        index = self.root / "memory" / "MEMORY.md"
        index.write_text("# Index\n\n[[missing-note]]\n" + "line\n" * 121, encoding="utf-8")
        issues = ctx.memory_check(self.root)
        codes = {issue["code"] for issue in issues}
        self.assertIn("missing", codes)
        self.assertIn("broken-link", codes)
        self.assertIn("index-too-long", codes)

    def test_rules_change_requires_approval(self):
        self.init_memory()
        rules = self.root / "memory" / "project-rules.md"
        rules.write_text(rules.read_text(encoding="utf-8") + "\nnew rule\n", encoding="utf-8")
        self.assertIn("rules-changed", {i["code"] for i in ctx.memory_check(self.root)})
        args = argparse.Namespace(path=str(self.root), user_approved=True)
        self.assertEqual(ctx.cmd_memory_rules_approve(args), 0)
        self.assertNotIn("rules-changed", {i["code"] for i in ctx.memory_check(self.root)})

    def test_rotate_moves_only_closed_entries(self):
        self.init_memory()
        journal = self.root / "memory" / "bugs.md"
        closed = "## BUG-20260615-001\n\n- Status: closed\n\n" + ("fixed\n" * 5000)
        opened = "## BUG-20260615-002\n\n- Status: open\n\nKeep this active.\n"
        journal.write_text("# Bug Log\n\n" + closed + "\n" + opened, encoding="utf-8")
        args = argparse.Namespace(path=str(self.root))
        self.assertEqual(ctx.cmd_memory_rotate(args), 0)
        active = journal.read_text(encoding="utf-8")
        self.assertNotIn("BUG-20260615-001", active)
        self.assertIn("BUG-20260615-002", active)
        archives = list((self.root / "memory" / "archive" / "bugs").glob("*.md"))
        self.assertEqual(len(archives), 1)
        self.assertIn("BUG-20260615-001", archives[0].read_text(encoding="utf-8"))

    def test_context_bundles_memory_and_topk_notes(self):
        self.init_memory()
        # a durable decision that should surface via local top-k retrieval
        (self.root / "memory" / "decisions.md").write_text(
            "# Decision Log\n\n## DEC-1 Caching boundary\n\n"
            "- Decision: keep the prompt prefix stable to preserve cache hits.\n",
            encoding="utf-8",
        )
        text = ctx._memory_context(self.root, "prompt cache prefix stable")
        self.assertIn("memory/MEMORY.md", text)
        self.assertIn("handoff.md", text)
        self.assertIn("memory/project-rules.md", text)
        self.assertIn("Relevant durable notes", text)
        self.assertIn("prompt prefix stable", text)
        self.assertNotIn("archive", text)

    def test_query_returns_local_topk_without_llm(self):
        self.init_memory()
        (self.root / "memory" / "investigations.md").write_text(
            "# Investigations\n\n## INV-7 Token budget\n\n"
            "- Findings: digest large files before reading them verbatim.\n",
            encoding="utf-8",
        )
        args = argparse.Namespace(
            path=str(self.root), scope="memory",
            question="digest large files budget", top=5, json=False,
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ctx.cmd_memory_query(args), 0)
        text = out.getvalue()
        self.assertIn("investigations.md", text)
        self.assertIn("digest large files", text)
        self.assertIn("local retrieval, no LLM", text)

    def test_query_project_scope_searches_repo_files(self):
        self.init_memory()
        (self.root / "app.py").write_text(
            "def widget_renderer():\n    return 'unique_marker_xyz'\n", encoding="utf-8")
        args = argparse.Namespace(
            path=str(self.root), scope="project",
            question="widget_renderer unique_marker_xyz", top=5, json=True,
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ctx.cmd_memory_query(args), 0)
        data = json.loads(out.getvalue())
        self.assertTrue(any(h["path"] == "app.py" for h in data["hits"]))

    @mock.patch("ctx._find_obsidian", return_value=None)
    def test_open_does_not_install_without_explicit_flag(self, find_obsidian):
        self.init_memory()
        args = argparse.Namespace(path=str(self.root), install_obsidian=False)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ctx.cmd_memory_open(args), 1)
        find_obsidian.assert_called_once()

    @mock.patch("ctx.subprocess.Popen")
    @mock.patch("ctx._restart_obsidian_if_running")
    @mock.patch("ctx._register_obsidian_vault",
                return_value=("0123456789abcdef", True))
    @mock.patch("ctx._find_obsidian", return_value="C:/Program Files/Obsidian/Obsidian.exe")
    def test_open_launches_existing_obsidian(
        self, find_obsidian, register, restart, popen
    ):
        self.init_memory()
        args = argparse.Namespace(path=str(self.root), install_obsidian=False)
        self.assertEqual(ctx.cmd_memory_open(args), 0)
        register.assert_called_once_with(self.root / "memory")
        restart.assert_called_once_with()
        command = popen.call_args.args[0]
        self.assertEqual(command[0], "C:/Program Files/Obsidian/Obsidian.exe")
        self.assertEqual(command[1], "obsidian://open?vault=memory")

    @mock.patch("ctx.subprocess.Popen")
    @mock.patch("ctx.subprocess.run")
    @mock.patch("ctx.shutil.which")
    @mock.patch("ctx._register_obsidian_vault",
                return_value=("0123456789abcdef", False))
    @mock.patch("ctx._find_obsidian")
    def test_open_installs_only_with_explicit_flag(
        self, find_obsidian, register, which, run, popen
    ):
        self.init_memory()
        find_obsidian.side_effect = [None, "C:/Obsidian.exe"]
        which.return_value = "C:/Windows/winget.exe"
        run.return_value = mock.Mock(returncode=0)
        args = argparse.Namespace(path=str(self.root), install_obsidian=True)
        self.assertEqual(ctx.cmd_memory_open(args), 0)
        run.assert_called_once()
        self.assertIn("Obsidian.Obsidian", run.call_args.args[0])
        popen.assert_called_once()

    @mock.patch("ctx.subprocess.Popen")
    @mock.patch("ctx._install_obsidian_from_official_release", return_value=0)
    @mock.patch("ctx.shutil.which", return_value=None)
    @mock.patch("ctx._register_obsidian_vault",
                return_value=("0123456789abcdef", False))
    @mock.patch("ctx._find_obsidian")
    def test_open_falls_back_to_official_release_without_winget(
        self, find_obsidian, register, which, install_release, popen
    ):
        self.init_memory()
        find_obsidian.side_effect = [None, "C:/Obsidian.exe"]
        args = argparse.Namespace(path=str(self.root), install_obsidian=True)
        self.assertEqual(ctx.cmd_memory_open(args), 0)
        install_release.assert_called_once_with()
        popen.assert_called_once()

    @mock.patch.dict(os.environ, {"APPDATA": ""}, clear=False)
    def test_register_vault_preserves_existing_entries(self):
        appdata = self.root / "appdata"
        with mock.patch.dict(os.environ, {"APPDATA": str(appdata)}, clear=False):
            config = appdata / "obsidian" / "obsidian.json"
            config.parent.mkdir(parents=True)
            config.write_text(
                '{"vaults":{"existing":{"path":"C:/notes","ts":1}}}',
                encoding="utf-8",
            )
            memory = self.root / "memory"
            memory.mkdir()
            vault_id, created = ctx._register_obsidian_vault(memory)
            data = json.loads(config.read_text(encoding="utf-8"))
            self.assertIn("existing", data["vaults"])
            self.assertEqual(len(vault_id), 16)
            self.assertTrue(created)
            self.assertTrue(any(
                value["path"] == str(memory.resolve())
                for value in data["vaults"].values()
            ))

    def test_rawcount_counts_directory_without_ledger(self):
        (self.root / "src").mkdir()
        (self.root / "src" / "app.ts").write_text("export const app = 1;\n", encoding="utf-8")
        (self.root / ".env").write_text("SECRET=value\n", encoding="utf-8")
        args = argparse.Namespace(path=str(self.root), include_secrets=False, json=False)

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(ctx.cmd_rawcount(args), 0)

        output = stdout.getvalue()
        self.assertIn("# raw context:", output)
        self.assertIn("files: 1", output)
        self.assertIn("secret-looking files skipped: 1", output)
        self.assertFalse((self.root / ".ctx" / "ledger.jsonl").exists())


class PackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self._cwd = os.getcwd()
        os.chdir(self.root)  # ledger is written to a cwd-relative .ctx

    def tearDown(self):
        os.chdir(self._cwd)
        self.temp.cleanup()

    def test_pack_is_deterministic_and_excludes_volatile_state(self):
        ctx.cmd_memory_init(argparse.Namespace(path="."))
        (self.root / "big.py").write_text("def a():\n    return 1\n" * 50, encoding="utf-8")
        (self.root / "handoff.md").write_text(
            "# Handoff\n\n## Now\n\nvolatile_task_marker\n", encoding="utf-8")
        args = argparse.Namespace(path=".", top=40, warn=4000, digest=0,
                                  out=None, quiet=False)

        with contextlib.redirect_stdout(io.StringIO()) as out1:
            self.assertEqual(ctx.cmd_pack(args), 0)
        with contextlib.redirect_stdout(io.StringIO()) as out2:
            self.assertEqual(ctx.cmd_pack(args), 0)

        body1 = out1.getvalue().split("# packet")[0]
        body2 = out2.getvalue().split("# packet")[0]
        self.assertEqual(body1, body2)  # byte-stable prefix across runs
        self.assertIn("PERMANENT RULES", body1)
        self.assertIn("MEMORY INDEX", body1)
        self.assertIn("REPO MAP", body1)
        # volatile handoff must NOT be baked into the cache-stable prefix
        self.assertNotIn("volatile_task_marker", body1)

    def test_pack_digest_appends_structure_and_logs_recon(self):
        (self.root / "mod.py").write_text(
            "import os\n\ndef exported():\n    secret = 1\n    return secret\n",
            encoding="utf-8")
        args = argparse.Namespace(path=".", top=40, warn=4000, digest=1,
                                  out="packet.md", quiet=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ctx.cmd_pack(args), 0)
        written = (self.root / "packet.md").read_text(encoding="utf-8")
        self.assertIn("DIGEST: mod.py", written)
        self.assertIn("def exported", written)
        self.assertNotIn("secret = 1", written)  # body is dropped, only structure kept
        recs = [json.loads(ln) for ln in
                (self.root / ".ctx" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertIn("pack", [r["op"] for r in recs])


class MeasureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _write_transcript(self, usages):
        path = self.root / "session.jsonl"
        lines = [json.dumps({"type": "assistant", "message": {"usage": u}})
                 for u in usages]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_measure_reads_real_usage_and_cache_rates(self):
        transcript = self._write_transcript([
            {"input_tokens": 100, "output_tokens": 50,
             "cache_read_input_tokens": 900, "cache_creation_input_tokens": 0},
            {"input_tokens": 100, "output_tokens": 50,
             "cache_read_input_tokens": 800, "cache_creation_input_tokens": 100},
        ])
        args = argparse.Namespace(transcript=str(transcript), usage_json=None,
                                  in_price=0.0, out_price=0.0)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ctx.cmd_measure(args), 0)
        text = out.getvalue()
        self.assertIn("2 assistant turn(s)", text)
        self.assertIn("2,000", text)          # input total = 200 + 1700 + 100
        self.assertIn("85.0%", text)          # cache-read share 1700/2000
        self.assertIn("94.4%", text)          # hit rate 1700/1800

    def test_measure_usage_json_from_stdin(self):
        usage = [{"input_tokens": 10, "output_tokens": 5,
                  "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}]
        args = argparse.Namespace(transcript=None, usage_json="-",
                                  in_price=3.0, out_price=15.0)
        with mock.patch("sys.stdin", io.StringIO(json.dumps(usage))):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(ctx.cmd_measure(args), 0)
        self.assertIn("1 assistant turn(s)", out.getvalue())

    def test_measure_reports_missing_usage_cleanly(self):
        args = argparse.Namespace(transcript=str(self.root / "nope.jsonl"),
                                  usage_json=None, in_price=0.0, out_price=0.0)
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(ctx.cmd_measure(args), 1)
        self.assertIn("no usage records", err.getvalue())


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self._cwd = os.getcwd()
        os.chdir(self.root)  # ledger is written to a cwd-relative .ctx

    def tearDown(self):
        os.chdir(self._cwd)
        self.temp.cleanup()

    def ledger_records(self):
        path = self.root / ".ctx" / "ledger.jsonl"
        if not path.is_file():
            return []
        return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()]

    def test_read_logs_uncompressed_pull(self):
        (self.root / "f.txt").write_text("hello world\n", encoding="utf-8")
        args = argparse.Namespace(file="f.txt")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ctx.cmd_read(args), 0)
        self.assertIn("hello world", out.getvalue())
        recs = self.ledger_records()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["op"], "read")
        # a raw read has no saving: it is the honest denominator
        self.assertEqual(recs[0]["raw_tokens"], recs[0]["kept_tokens"])
        self.assertEqual(recs[0]["saved_tokens"], 0)

    def test_map_logs_recon_record(self):
        (self.root / "a.py").write_text("def a():\n    pass\n", encoding="utf-8")
        args = argparse.Namespace(path=".", top=40, all=False, warn=4000)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ctx.cmd_map(args), 0)
        ops = [r["op"] for r in self.ledger_records()]
        self.assertIn("map", ops)

    def test_ledger_log_keeps_extra_fields_and_drops_none(self):
        ctx.ledger_log("pack", 100, 10, "q", files=3, digests=None)
        rec = self.ledger_records()[0]
        self.assertEqual(rec["files"], 3)
        self.assertNotIn("digests", rec)  # None extras are dropped
        self.assertEqual(rec["v"], 2)

    def test_hook_logs_direct_pull_from_stdin(self):
        payload = {
            "session_id": "abc",
            "tool_name": "Read",
            "tool_response": {"file": {"content": "x " * 500}},
        }
        args = argparse.Namespace(min_tokens=10)
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))):
            self.assertEqual(ctx.cmd_hook(args), 0)
        recs = self.ledger_records()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["op"], "direct")
        self.assertEqual(recs[0]["raw_tokens"], recs[0]["kept_tokens"])
        self.assertEqual(recs[0]["session"], "abc")

    def test_hook_is_silent_on_garbage_and_below_threshold(self):
        with mock.patch("sys.stdin", io.StringIO("not json")):
            self.assertEqual(ctx.cmd_hook(argparse.Namespace(min_tokens=10)), 0)
        tiny = {"tool_name": "Read", "tool_response": "hi"}
        with mock.patch("sys.stdin", io.StringIO(json.dumps(tiny))):
            self.assertEqual(ctx.cmd_hook(argparse.Namespace(min_tokens=200)), 0)
        self.assertEqual(self.ledger_records(), [])  # nothing logged either way

    def test_hook_skips_ctx_selfcall_to_avoid_double_count(self):
        # `ctx digest` run via Bash already self-logs; the hook must not also
        # count its output as a raw "direct" pull.
        payload = {
            "tool_name": "Bash",
            "tool_input": {"command": "ctx digest big.py"},
            "tool_response": {"stdout": "signature " * 200},
        }
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))):
            self.assertEqual(ctx.cmd_hook(argparse.Namespace(min_tokens=10)), 0)
        self.assertEqual(self.ledger_records(), [])  # nothing logged
        # a non-ctx Bash command IS counted
        payload["tool_input"]["command"] = "cat big.py"
        with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))):
            self.assertEqual(ctx.cmd_hook(argparse.Namespace(min_tokens=10)), 0)
        self.assertEqual([r["op"] for r in self.ledger_records()], ["direct"])

    def test_report_splits_content_flow_from_recon_and_dedups(self):
        ctx.ledger_log("read", 100, 100, "f.txt")          # raw pull
        ctx.ledger_log("digest", 100, 20, "f.py")           # compressed pull
        ctx.ledger_log("map", 50000, 80, "/repo")           # recon, must not inflate %
        ctx.ledger_log("pack", 60000, 300, "/repo")         # recon, must not inflate %
        ctx.ledger_log("direct", 30, 30, "Read", tool_id="T9")
        ctx.ledger_log("direct", 30, 30, "Read", tool_id="T9")  # duplicate, must drop
        args = argparse.Namespace(price=5.0, reset=False, settle=0)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ctx.cmd_report(args), 0)
        text = out.getvalue()
        self.assertIn("CONTENT FLOW", text)
        self.assertIn("RECONNAISSANCE", text)               # map/pack reported separately
        self.assertIn("tracked file-content coverage", text)
        # content saved = (100+100+30) - (100+20+30) = 80 of 230 -> 34.8%
        self.assertIn("34.8%", text)
        self.assertIn("de-duplicated 1", text)              # the repeated T9 dropped


if __name__ == "__main__":
    unittest.main()

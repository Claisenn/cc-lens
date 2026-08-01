import io
import json
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "bin" / "cclens"

CCLENS = SourceFileLoader("cclens", str(MODULE_PATH)).load_module()


class LaunchTests(unittest.TestCase):
    def test_should_pick_on_launch(self):
        with mock.patch.object(CCLENS.sys.stdin, "isatty", return_value=True), \
             mock.patch.object(CCLENS.sys.stdout, "isatty", return_value=True):
            self.assertTrue(CCLENS.should_pick_on_launch("claude", []))
            self.assertTrue(CCLENS.should_pick_on_launch("codex", ["--model", "gpt-5"]))
            self.assertFalse(CCLENS.should_pick_on_launch("claude", ["--resume", "abc"]))
            self.assertFalse(CCLENS.should_pick_on_launch("claude", ["--print", "hello"]))
            self.assertFalse(CCLENS.should_pick_on_launch("claude", ["--from-pr", "123"]))
            self.assertFalse(CCLENS.should_pick_on_launch("codex", ["resume", "--last"]))
            self.assertFalse(CCLENS.should_pick_on_launch("codex", ["exec", "hello"]))

    def test_launch_hook_consumes_ticket_once_without_user_prompt(self):
        with tempfile.TemporaryDirectory() as td:
            launch_dir = Path(td) / "launch"
            launch_dir.mkdir(parents=True)
            ticket = launch_dir / "handoff-test.txt"
            ticket.write_text("summary text")
            os.chmod(ticket, 0o600)
            with mock.patch.object(CCLENS, "LENS_HOME", td), \
                 mock.patch.dict(os.environ, {"CC_LENS_HANDOFF_TICKET": str(ticket)}), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                CCLENS.cmd_handoff(["--launch-hook"])
                first = stdout.getvalue()
            self.assertIn("[cc-lens handoff]\\nsummary text", first)
            self.assertFalse(ticket.exists())
            with mock.patch.object(CCLENS, "LENS_HOME", td), \
                 mock.patch.dict(os.environ, {"CC_LENS_HANDOFF_TICKET": str(ticket)}), \
                 mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
                CCLENS.cmd_handoff(["--launch-hook"])
                second = stdout.getvalue()
            self.assertEqual(second, "")

    def test_shell_init_outputs_launch_wrappers(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            CCLENS.cmd_shell_init([])
        text = stdout.getvalue()
        self.assertIn("launch claude", text)
        self.assertIn("launch codex", text)

    def test_cmd_install_codex_writes_launch_hook_and_trusts(self):
        with tempfile.TemporaryDirectory() as home:
            codex_home = Path(home) / ".codex"
            with mock.patch.object(CCLENS, "HOME", home), \
                 mock.patch("sys.stdout", new_callable=io.StringIO):
                CCLENS.cmd_install(["codex"])

            hooks_path = codex_home / "hooks.json"
            config_path = codex_home / "config.toml"
            hooks = json.loads(hooks_path.read_text())
            session_groups = hooks["hooks"]["SessionStart"]
            self.assertEqual(len(session_groups), 1)
            self.assertEqual(session_groups[0]["matcher"], "startup")
            handler = session_groups[0]["hooks"][0]
            self.assertTrue(handler["command"].endswith("handoff --launch-hook"))

            config_text = config_path.read_text()
            session_key = f'{hooks_path}:session_start:0:0'
            session_hash = CCLENS.command_hook_trusted_hash(
                "SessionStart", "startup", handler["command"], 20, "cc-lens sessionstart"
            )
            self.assertIn(f'[hooks.state."{session_key}"]', config_text)
            self.assertIn(f'trusted_hash = "{session_hash}"', config_text)

            pre_key = f'{hooks_path}:pre_tool_use:0:0'
            stop_key = f'{hooks_path}:stop:0:0'
            self.assertIn(f'[hooks.state."{pre_key}"]', config_text)
            self.assertIn(f'[hooks.state."{stop_key}"]', config_text)


if __name__ == "__main__":
    unittest.main()

"""Tests for mods/codex-limits/codex_limits.py against a fake `codex` executable.

Run from the repo root: python3 -m unittest discover -s tests -v
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(ROOT, "mods", "codex-limits", "codex_limits.py")
FAKE = os.path.join(ROOT, "tests", "fake_codex.py")


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers kill(0); it has exited.
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split(") ", 1)[1][0] != "Z"
    except OSError:
        return True


class HelperTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.bin = os.path.join(self.tmp, "bin")
        os.mkdir(self.bin)
        codex = os.path.join(self.bin, "codex")
        with open(FAKE) as src, open(codex, "w") as dst:
            dst.write(f"#!{sys.executable}\n" + src.read())
        os.chmod(codex, os.stat(codex).st_mode | stat.S_IXUSR)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_helper(self, mode="normal", path=None, **env):
        full_env = {k: v for k, v in os.environ.items() if k != "CODEX_BIN"}
        full_env.update({"PATH": path if path is not None else self.bin, "FAKE_CODEX_MODE": mode, "SHELL": "/nonexistent"})
        full_env.update(env)
        started = time.monotonic()
        proc = subprocess.run([sys.executable, HELPER], env=full_env, capture_output=True, text=True, timeout=30)
        self.elapsed = time.monotonic() - started
        self.assertEqual(proc.stderr, "")
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 1, proc.stdout)
        return json.loads(lines[0])

    def test_normal_response(self):
        out = self.run_helper("normal")
        self.assertEqual(out["windows"], {
            "5h": {"usedPercent": 37, "resetsAt": 1794216706},
            "wk": {"usedPercent": 33, "resetsAt": 1794401472},
        })
        self.assertEqual(out["plan"], "plus")
        self.assertIsInstance(out["fetchedAt"], int)

    def test_windows_mapped_by_duration_when_swapped(self):
        out = self.run_helper("swapped")
        self.assertEqual(out["windows"]["5h"]["usedPercent"], 37)
        self.assertEqual(out["windows"]["wk"]["usedPercent"], 33)

    def test_null_secondary(self):
        out = self.run_helper("null_secondary")
        self.assertEqual(list(out["windows"]), ["5h"])

    def test_null_or_malformed_durations_are_ignored(self):
        out = self.run_helper("odd_durations")
        self.assertEqual(out["error"], "not_signed_in")

    def test_auth_error_is_not_signed_in(self):
        out = self.run_helper("error")
        self.assertEqual(out["error"], "not_signed_in")
        self.assertNotIn("windows", out)

    def test_other_error_is_failed(self):
        self.assertEqual(self.run_helper("other_error")["error"], "failed")

    def test_notifications_before_result_are_skipped(self):
        out = self.run_helper("notifications")
        self.assertEqual(out["windows"]["5h"]["usedPercent"], 37)
        self.assertEqual(out["windows"]["wk"]["usedPercent"], 33)

    def test_child_exit_is_failed(self):
        self.assertEqual(self.run_helper("exit")["error"], "failed")

    def assert_hang_kills_child_tree(self, mode):
        pidfile = os.path.join(self.tmp, "pids")
        out = self.run_helper(mode, CODEX_LIMITS_TIMEOUT="1.5", FAKE_CODEX_PIDFILE=pidfile)
        self.assertEqual(out["error"], "timeout")
        self.assertLess(self.elapsed, 8)
        with open(pidfile) as f:
            fake_pid, grandchild_pid = map(int, f.read().split())
        self.assertFalse(alive(fake_pid), "fake codex still running")
        self.assertFalse(alive(grandchild_pid), "codex's own child still running")

    def test_hang_times_out_and_kills_child_tree(self):
        self.assert_hang_kills_child_tree("hang")

    def test_hang_kills_child_that_ignores_sigterm(self):
        # The launcher exits on SIGTERM; its child ignores it and must still be killed.
        self.assert_hang_kills_child_tree("hang_stubborn_child")

    def test_codex_missing_from_path(self):
        out = self.run_helper(path=os.path.join(self.tmp, "empty"))
        self.assertEqual(out["error"], "codex_missing")

    def test_codex_bin_override(self):
        out = self.run_helper(path=os.path.join(self.tmp, "empty"), CODEX_BIN=os.path.join(self.bin, "codex"))
        self.assertIn("5h", out["windows"])

    def test_codex_bin_override_missing(self):
        out = self.run_helper(CODEX_BIN=os.path.join(self.tmp, "nope"))
        self.assertEqual(out["error"], "codex_missing")

    def test_login_shell_fallback(self):
        shell = os.path.join(self.tmp, "fakeshell")
        with open(shell, "w") as f:
            f.write(f"#!/bin/sh\necho 'greeting noise'\necho '{self.bin}/codex'\n")
        os.chmod(shell, 0o755)
        out = self.run_helper(path=os.path.join(self.tmp, "empty"), SHELL=shell)
        self.assertIn("wk", out["windows"])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Print the signed-in Codex (ChatGPT plan) usage limits as one JSON line.

Asks the local `codex app-server` over stdio (newline-delimited JSON-RPC):
initialize -> initialized -> account/rateLimits/read. Makes no model request
and no network call of its own; Codex uses and refreshes its own login.

Output, always exactly one line on stdout:
  {"windows": {"5h": {"usedPercent": 37, "resetsAt": 1794216706},
               "wk": {"usedPercent": 33, "resetsAt": 1794401472}},
   "plan": "plus", "fetchedAt": 1794200000}
or
  {"error": "not_signed_in" | "codex_missing" | "timeout" | "failed", "detail": "..."}

Environment:
  CODEX_BIN              path to the codex executable (else PATH, else the login shell's PATH)
  CODEX_LIMITS_TIMEOUT   overall timeout in seconds (default 15)
"""

import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

WINDOW_KEYS = {300: "5h", 10080: "wk"}
AUTH_HINT = re.compile(r"auth|log ?in|logged|sign|api key|unauthori[sz]ed|401|chatgpt account", re.I)
DEFAULT_TIMEOUT = 15.0


class Failure(Exception):
    def __init__(self, code, detail=""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def is_exe(path):
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def find_codex(deadline):
    """CODEX_BIN, else PATH, else the login shell's PATH (desktop launches may lack it)."""
    override = os.environ.get("CODEX_BIN")
    if override:
        if is_exe(override):
            return override
        raise Failure("codex_missing", "CODEX_BIN is not an executable")
    found = shutil.which("codex")
    if found:
        return found
    shell = os.environ.get("SHELL")
    if shell and is_exe(shell) and os.name != "nt":
        try:
            out = subprocess.run(
                [shell, "-lc", "command -v codex"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=max(0.1, min(5.0, deadline - time.monotonic())),
            ).stdout
            lines = [line.strip() for line in out.splitlines() if line.strip()]
            if lines and os.path.isabs(lines[-1]) and is_exe(lines[-1]):
                return lines[-1]
        except (OSError, subprocess.SubprocessError):
            pass
    raise Failure("codex_missing", "codex not found on PATH")


def kill_tree(proc):
    """Stop the child and anything it started (the pnpm/npm shim runs node, which runs codex)."""
    try:
        if proc.stdin:
            proc.stdin.close()
    except OSError:
        pass
    killpg = getattr(os, "killpg", None)  # absent on Windows
    if proc.poll() is None:
        if killpg is None:
            proc.kill()
        else:
            try:
                killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=1.0)
            except (ProcessLookupError, PermissionError, subprocess.TimeoutExpired):
                pass
    if killpg is not None:
        # The shim may have exited and left children in the group, some ignoring SIGTERM.
        try:
            killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        pass


class Rpc:
    def __init__(self, proc, deadline):
        self.proc = proc
        self.deadline = deadline
        self.lines = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        try:
            for line in self.proc.stdout:
                self.lines.put(line)
        except (OSError, ValueError):
            pass
        self.lines.put(None)

    def send(self, message):
        try:
            self.proc.stdin.write(json.dumps(message) + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError):
            raise Failure("failed", "codex app-server closed its input")

    def wait_for(self, request_id):
        """The response with this id; notifications and other lines are skipped."""
        while True:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise Failure("timeout", "codex app-server did not answer in time")
            try:
                line = self.lines.get(timeout=remaining)
            except queue.Empty:
                raise Failure("timeout", "codex app-server did not answer in time")
            if line is None:
                raise Failure("failed", "codex app-server exited")
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if not isinstance(message, dict) or message.get("id") != request_id:
                continue
            if "error" in message:
                error = message.get("error") or {}
                text = str(error.get("message", error) if isinstance(error, dict) else error)[:200]
                raise Failure("not_signed_in" if AUTH_HINT.search(text) else "failed", text)
            return message.get("result") or {}


def normalize(result):
    limits = result.get("rateLimits") if isinstance(result, dict) else None
    if not isinstance(limits, dict):
        raise Failure("not_signed_in", "no rate limits for this account")
    windows = {}
    for slot in ("primary", "secondary"):
        window = limits.get(slot)
        if not isinstance(window, dict):
            continue
        mins = window.get("windowDurationMins")
        key = WINDOW_KEYS.get(mins) if isinstance(mins, int) else None
        used, resets = window.get("usedPercent"), window.get("resetsAt")
        if key and isinstance(used, (int, float)) and isinstance(resets, (int, float)):
            windows[key] = {"usedPercent": used, "resetsAt": int(resets)}
    if not windows:
        raise Failure("not_signed_in", "no usage windows for this account")
    return {"windows": windows, "plan": limits.get("planType"), "fetchedAt": int(time.time())}


def fetch():
    try:
        timeout = float(os.environ.get("CODEX_LIMITS_TIMEOUT") or DEFAULT_TIMEOUT)
    except ValueError:
        timeout = DEFAULT_TIMEOUT
    deadline = time.monotonic() + timeout
    codex = find_codex(deadline)
    try:
        proc = subprocess.Popen(
            [codex, "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=os.name != "nt",
        )
    except OSError as e:
        raise Failure("codex_missing", f"cannot start codex: {e.strerror or e}")
    try:
        rpc = Rpc(proc, deadline)
        rpc.send({
            "method": "initialize",
            "id": 0,
            "params": {"clientInfo": {"name": "herdr-codex-limits", "title": "Herdr Codex limits", "version": "0.1.0"}},
        })
        rpc.wait_for(0)
        rpc.send({"method": "initialized", "params": {}})
        rpc.send({"method": "account/rateLimits/read", "id": 1})
        return normalize(rpc.wait_for(1))
    finally:
        kill_tree(proc)


def main():
    try:
        out = fetch()
    except Failure as f:
        out = {"error": f.code, "detail": f.detail}
    except Exception as e:  # never let a traceback reach stdout/stderr consumers
        out = {"error": "failed", "detail": type(e).__name__}
    sys.stdout.write(json.dumps(out, separators=(",", ":")) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""A stand-in for `codex app-server`, driven by FAKE_CODEX_MODE."""

import json
import os
import subprocess
import sys
import time

MODE = os.environ.get("FAKE_CODEX_MODE", "normal")
PRIMARY = {"usedPercent": 37, "windowDurationMins": 300, "resetsAt": 1794216706}
SECONDARY = {"usedPercent": 33, "windowDurationMins": 10080, "resetsAt": 1794401472}


def out(message):
    sys.stdout.write((message if isinstance(message, str) else json.dumps(message)) + "\n")
    sys.stdout.flush()


def limits(primary, secondary):
    return {"rateLimits": {"limitId": "codex", "primary": primary, "secondary": secondary, "planType": "plus"}}


if sys.argv[1:] != ["app-server"]:
    sys.exit(2)

if MODE in ("hang", "hang_stubborn_child"):
    ignore_term = "import signal; signal.signal(signal.SIGTERM, signal.SIG_IGN); " if MODE == "hang_stubborn_child" else ""
    child = subprocess.Popen([sys.executable, "-c", ignore_term + "import time; time.sleep(300)"])
    with open(os.environ["FAKE_CODEX_PIDFILE"], "w") as f:
        f.write(f"{os.getpid()} {child.pid}\n")
    time.sleep(300)
    sys.exit(0)

for line in sys.stdin:
    request = json.loads(line)
    rid = request.get("id")
    if rid == 0:
        out({"method": "remoteControl/status/changed", "params": {}})
        out({"id": 0, "result": {"userAgent": "fake"}})
    elif rid == 1:
        if MODE == "normal":
            out({"id": 1, "result": limits(PRIMARY, SECONDARY)})
        elif MODE == "swapped":
            out({"id": 1, "result": limits(SECONDARY, PRIMARY)})
        elif MODE == "null_secondary":
            out({"id": 1, "result": limits(PRIMARY, None)})
        elif MODE == "odd_durations":
            out({"id": 1, "result": limits(dict(PRIMARY, windowDurationMins=None), dict(SECONDARY, windowDurationMins=[10080]))})
        elif MODE == "error":
            out({"id": 1, "error": {"code": -32600, "message": "codex account authentication required to read rate limits"}})
        elif MODE == "other_error":
            out({"id": 1, "error": {"code": -32603, "message": "internal error"}})
        elif MODE == "notifications":
            out({"method": "account/updated", "params": {"authMode": "chatgpt"}})
            out("not json at all")
            out({"method": "account/rateLimits/updated", "params": {"rateLimits": limits(None, None)}})
            out({"id": 7, "result": {"rateLimits": {"primary": {"usedPercent": 99, "windowDurationMins": 300, "resetsAt": 1}}}})
            out({"id": 1, "result": limits(PRIMARY, SECONDARY)})
        elif MODE == "exit":
            sys.exit(1)

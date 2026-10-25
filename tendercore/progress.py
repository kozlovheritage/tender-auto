# TA_FRIENDLY_PROGRESS
"""Opt-in progress events; never contains document contents or credentials."""
import json
import os


def emit(text, kind="info", decision=None):
    if os.environ.get("TA_GUI_PROGRESS") != "1":
        return
    payload = {"text": str(text), "kind": kind}
    if decision is not None:
        payload["decision"] = str(decision)
    try:
        print("@@TA_PROGRESS@@" + json.dumps(payload, ensure_ascii=True), flush=True)
    except (OSError, UnicodeError):
        # A closed output pipe must not change an analysis decision.
        pass

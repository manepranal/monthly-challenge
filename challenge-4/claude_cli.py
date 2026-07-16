"""Shared `claude` CLI fallback used when ANTHROPIC_API_KEY is missing or 401s.

Claude Code's CLI authenticates via OAuth, so it keeps the demo running end-to-end
even with no working SDK key. The CLI can occasionally return empty/partial output
under load, so we retry a few times and parse defensively.
"""

import json
import os
import subprocess
import time


def run_cli_json(prompt: str, attempts: int = 3, timeout: int = 180) -> dict:
    """Run `claude -p <prompt> --output-format json` and return the model's parsed
    JSON result. Retries on empty or non-JSON output. Raises after `attempts`.

    Retries back off (20s, 40s) rather than firing immediately: the CLI's
    failures come in rate-limit windows, and three instant retries all land
    inside the same window — observed in watch mode, where that pattern burned
    a whole run budget per outage. Spacing the attempts lets one step survive
    a transient window instead of escalating to a park."""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    last = "no attempt ran"
    for attempt in range(attempts):
        if attempt:
            time.sleep(20 * attempt)
        proc = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, env=env, timeout=timeout, check=False,
        )
        if proc.returncode != 0:
            last = f"exit {proc.returncode}: {proc.stderr[:200].strip()}"
            continue
        sout = proc.stdout.strip()
        if not sout:
            last = "empty stdout"
            continue
        try:
            out = json.loads(sout)
        except json.JSONDecodeError:
            last = "CLI wrapper was not JSON"
            continue
        if out.get("is_error"):
            last = f"CLI error: {str(out.get('result'))[:150]}"
            continue
        raw = (out.get("result") or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            last = "model result was not JSON"
            continue
    raise RuntimeError(f"claude CLI fallback failed after {attempts} attempts ({last})")

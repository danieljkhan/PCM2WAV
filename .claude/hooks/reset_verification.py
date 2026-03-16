"""Post-edit verification reset hook for Claude Code.

When any file is modified via Edit or Write tool, resets the verification
status so that the verification chain must be re-run before committing.

Adapted for PCM2WAV project.
Exceptions: files inside .claude/ directory are not tracked (hook infra).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

VERIFICATION_STATUS_PATH = Path(__file__).parent.parent / "verification-status.json"

IGNORED_PATHS = [".claude/", "docs/runbooks/weekly/"]


def reset_status(file_path: str) -> None:
    """Reset verification status after a file edit."""
    if not VERIFICATION_STATUS_PATH.exists():
        return

    if any(ignored in file_path.replace("\\", "/") for ignored in IGNORED_PATHS):
        return

    now = datetime.now(tz=timezone.utc).isoformat()

    status = {
        "verified": False,
        "verifiers": {
            "qa_subagent": {"completed": False, "timestamp": None, "result": None},
            "qc_subagent": {"completed": False, "timestamp": None, "result": None},
            "review_subagent": {
                "completed": False,
                "timestamp": None,
                "result": None,
            },
        },
        "rounds_completed": 0,
        "polish_loop": {
            "terminated": False,
            "consecutive_zero_fix_cycles": 0,
        },
        "last_reset": now,
        "reset_reason": f"File modified: {file_path}",
    }

    with open(VERIFICATION_STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)


def main() -> None:
    """Main hook entry point. Reads stdin JSON, resets if file was edited."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)

        hook_input = json.loads(raw)
        tool_input = hook_input.get("tool_input", {})

        file_path = tool_input.get("file_path", "")
        if file_path:
            reset_status(file_path)

    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()

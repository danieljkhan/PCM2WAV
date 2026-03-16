"""Post-commit hook that directs automatic worklog update.

Runs after Bash tool calls. When a successful git commit is
detected, outputs a directive so the orchestrator immediately
updates the worklog in docs/runbooks/weekly/ before continuing.

Adapted for PCM2WAV project.
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone

COMMIT_PATTERN = re.compile(r"\bgit\b.*\bcommit\b", re.IGNORECASE)
COMMIT_HASH_PATTERN = re.compile(r"\b([0-9a-f]{7,40})\b")


def main() -> None:
    """Detect git commit and output auto-update directive."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)

        hook_input = json.loads(raw)
        tool_name = hook_input.get("tool_name", "")
        tool_input = hook_input.get("tool_input", {})

        if tool_name != "Bash":
            sys.exit(0)

        command = tool_input.get("command", "")
        if not COMMIT_PATTERN.search(command):
            sys.exit(0)

        # Claude Code PostToolUse schema: try "tool_result" first, fallback to "tool_output"
        result = hook_input.get("tool_result", hook_input.get("tool_output", {}))
        stdout = result.get("stdout", "") if isinstance(result, dict) else ""
        if "nothing to commit" in stdout:
            sys.exit(0)

        # Extract commit hash from output
        commit_hash = "unknown"
        for line in stdout.splitlines():
            match = COMMIT_HASH_PATTERN.search(line)
            if match:
                commit_hash = match.group(1)
                break

        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst).strftime("%Y-%m-%d %H:%M KST")

        sys.stdout.write(
            f"[WORKLOG AUTO-UPDATE] 커밋 감지: {commit_hash} ({now}). "
            "즉시 docs/runbooks/weekly/ 의 당일 작업일지를 자동 업데이트하라. "
            "작업일지가 없으면 신규 생성하라. "
            "필수 기재 항목: (1) 커밋 해시 (2) 변경 요약 "
            f"(3) 검증 결과 (4) 잔여 작업 (5) 업데이트 시각: {now}. "
            "이 업데이트는 사용자에게 응답하기 전에 완료해야 한다.\n"
        )
        sys.exit(0)

    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()

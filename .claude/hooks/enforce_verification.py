"""Pre-commit verification enforcement hook for Claude Code.

Blocks git commit and git push commands unless:
1. All 3 verification rounds have completed (each round = qa, qc, review)
   with no BLOCK items in the final round (Round 3).
2. The iterative polish loop has terminated (2 consecutive 0-fix cycles).

Exceptions:
- Docs-only commits (all staged files under docs/) are exempt from both
  the verification chain and the polish loop.

Adapted for PCM2WAV project.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

VERIFICATION_STATUS_PATH = Path(__file__).parent.parent / "verification-status.json"

BLOCKED_PATTERNS = [
    re.compile(r"\bgit\b.*\bcommit\b", re.IGNORECASE),
    re.compile(r"\bgit\b.*\bpush\b", re.IGNORECASE),
    re.compile(r"\bgh\b.*\bpr\b.*\bmerge\b", re.IGNORECASE),
]

REQUIRED_VERIFIERS = ["qa_subagent", "qc_subagent", "review_subagent"]
REQUIRED_ROUNDS = 3

DOCS_ONLY_PREFIXES = ["docs/", ".claude/"]


def load_status() -> dict:
    """Load verification status from JSON file.

    Returns fail-safe (unverified) dict on missing or malformed file.
    """
    if not VERIFICATION_STATUS_PATH.exists():
        return {"verified": False, "verifiers": {}, "rounds_completed": 0}
    try:
        with open(VERIFICATION_STATUS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"verified": False, "verifiers": {}, "rounds_completed": 0}


def is_docs_only_commit() -> bool:
    """Check if the staged changes are docs-only (exempt from verification).

    Runs ``git diff --cached --name-only`` to get staged file list.
    Returns True if ALL staged files are under docs/ or .claude/ directories.
    Returns False on any error (fail-safe: treat as non-docs commit).
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False
        files = [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
        if not files:
            return False
        return all(
            any(f.replace("\\", "/").startswith(prefix) for prefix in DOCS_ONLY_PREFIXES)
            for f in files
        )
    except Exception:
        return False


def check_verification(status: dict) -> tuple[bool, str]:
    """Check if all verification steps are complete.

    Returns:
        Tuple of (is_verified, reason_if_blocked).

    When all conditions are met (3 rounds completed, all verifiers done,
    0 BLOCK items, polish loop terminated), auto-approves by returning
    (True, ""). The ``verified`` flag in the JSON is also accepted as
    an explicit override.
    """
    # Explicit override flag
    if status.get("verified", False):
        return True, ""

    # Check 3-round completion
    rounds_completed = status.get("rounds_completed", 0)
    if rounds_completed < REQUIRED_ROUNDS:
        return False, (
            f"[VERIFICATION HOOK] 검증 체인 {rounds_completed}/{REQUIRED_ROUNDS} 라운드 완료.\n"
            f"3라운드 검증 체인(QA→QC→Review × 3)을 모두 완료해야 커밋할 수 있습니다.\n"
            f"현재 라운드: {rounds_completed + 1}/{REQUIRED_ROUNDS}"
        )

    # Check that all verifiers in the final round completed
    missing = []
    verifiers = status.get("verifiers", {})
    for vid in REQUIRED_VERIFIERS:
        v = verifiers.get(vid, {})
        if not v.get("completed", False):
            missing.append(vid)

    if missing:
        names = ", ".join(missing)
        return False, (
            f"[VERIFICATION HOOK] Round 3 검증 미완료 서브에이전트: {names}\n"
            f"3개 검증 서브에이전트(qa, qc, review)가 모두 완료해야 커밋할 수 있습니다.\n"
            f"검증 완료 후 verification-status.json을 업데이트하세요."
        )

    # Check for BLOCK items in final round
    block_count = 0
    for vid in REQUIRED_VERIFIERS:
        v = verifiers.get(vid, {})
        block_count += v.get("block_count", 0)

    if block_count > 0:
        return False, (
            f"[VERIFICATION HOOK] Round 3에서 BLOCK {block_count}건 미해결.\n"
            f"BLOCK 잔존 시 Round 1부터 재시작해야 합니다."
        )

    # Check polish loop completion
    polish = status.get("polish_loop", {})
    if not polish.get("terminated", False):
        zero_cycles = polish.get("consecutive_zero_fix_cycles", 0)
        return False, (
            f"[VERIFICATION HOOK] Iterative polish loop 미완료.\n"
            f"현재 연속 0-fix cycles: {zero_cycles}/2\n"
            f"2 consecutive 0-fix cycles 달성 후 커밋할 수 있습니다."
        )

    # All conditions met — auto-approve
    return True, ""


def is_blocked_command(command: str) -> bool:
    """Check if the bash command is a git commit/push/merge."""
    return any(pattern.search(command) for pattern in BLOCKED_PATTERNS)


def main() -> None:
    """Main hook entry point. Reads stdin JSON, checks verification."""
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
        if not is_blocked_command(command):
            sys.exit(0)

        # Docs-only commits are exempt from verification
        if is_docs_only_commit():
            sys.exit(0)

        status = load_status()
        verified, reason = check_verification(status)

        if verified:
            sys.exit(0)
        else:
            sys.stderr.write(reason + "\n")
            sys.exit(2)

    except Exception as exc:
        sys.stderr.write(
            f"[VERIFICATION HOOK] 예상치 못한 오류 — 안전을 위해 차단합니다: {exc}\n"
        )
        sys.exit(2)


if __name__ == "__main__":
    main()

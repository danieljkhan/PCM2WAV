# PCM2WAV Sub-Agent Setup

> Purpose: PCM to WAV 변환 GUI 도구 개발.
> All work must produce correct, well-tested conversion logic and a clean Tkinter GUI.

This setup applies to the project root directory (`.`).

## Operating Model

A single Claude Code session (Opus 4.6) acts as the **orchestrator**. It spawns specialized sub-agents via the Agent tool for parallel task execution. Sub-agents report results directly back to the orchestrator — no file-based board or separate terminal sessions needed.

## Sub-Agent Types

### feature

- Implements converter engine, presets, GUI widgets, and main app.
- Scope: `pcm2wav/`, `main.py`, `pyproject.toml`
- Focus: PCM→WAV conversion logic, byte order handling, 8-bit signedness, chunk alignment, Tkinter GUI, presets, batch processing, thread-safe progress/cancel.

### qa

- Writes tests for new and changed behavior.
- Scope: `tests/` only.
- Does not edit production code.

### qc

- Executes the verification suite and reports results.
- Runs: `ruff check .`, `ruff format --check .`, `mypy pcm2wav/`, `pytest tests/ -v`
- Reports pass/fail to orchestrator.
- Does not write files.

### review

- Read-only inspection across the entire repository.
- Focus areas:
  - CLAUDE.md / AGENTS.md compliance
  - Architecture constraints (dependency direction, circular imports, GUI-engine separation)
  - Security audit (path traversal, injection, unsafe file operations)
  - WAV format correctness (header fields, byte order, signedness rules)
  - Edge cases (empty files, 4GB limit, frame misalignment, unicode paths)
- Reports PASS / WARN / BLOCK findings.

## Orchestrator Workflow

1. **Plan**: Identify priorities from the development plan, get user approval.
2. **Assign**: Compose sub-agent prompts with scope, goal, and constraints.
3. **Execute**: Spawn independent sub-agents in parallel. Use `isolation: "worktree"` for overlapping scopes.
4. **Verify**: Run 3-round verification chain (QA → QC → Review × 3, with developer fixes between rounds).
5. **Accept**: Accept only if Round 3 QC and Review report no BLOCK items.
6. **Polish**: Run iterative polish loop on all changed files until termination (2 consecutive 0-fix cycles).
7. **Commit**: Only after polish loop terminates. Committing before termination is a process violation.
8. **Report**: Summarize results to user in Korean.

## Mandatory Verification Chain — 3-Round

Every code, config, or dependency deliverable must complete 3 full rounds of verification. The orchestrator's own visual review does NOT count as verification.

**Round 1:**
1. **qa sub-agent** writes tests for new or changed behavior.
2. **qc sub-agent** runs lint, type checks, and tests.
3. **review sub-agent** performs independent read-only inspection.
4. **Developer fix** — orchestrator fixes all BLOCK and applicable WARN items.

**Round 2:**
5. **qa sub-agent** updates/adds tests for code changed during fix.
6. **qc sub-agent** re-runs full suite on fixed code.
7. **review sub-agent** re-inspects; confirms Round 1 issues resolved.
8. **Developer fix** — orchestrator fixes any remaining issues.

**Round 3 (final):**
9. **qa sub-agent** final test pass for Round 2 fix changes.
10. **qc sub-agent** final run. Must PASS with 0 failures.
11. **review sub-agent** final inspection. Must report 0 BLOCK items.
12. **Orchestrator acceptance** — accept only if Round 3 has no BLOCK items.

If Round 3 still has BLOCK items, the cycle restarts from Round 1.

## Iterative Polish Loop

After the verification chain passes, the orchestrator runs a polish loop:

1. **One iteration** = review all changed files → fix issues → re-run QC.
2. **One cycle** = 10 iterations.
3. **Termination**: 2 consecutive 0-fix cycles (20 iterations with 0 modifications).
4. **Commit gate**: Commit only after the loop terminates. Committing before is a process violation.

Documentation-only or worklog-only commits are exempt.

## Scope Safety Rules

1. Each sub-agent prompt must list exact files or directories it may edit.
2. Sub-agents must not expand scope beyond assignment.
3. The orchestrator must not spawn write sub-agents with overlapping scopes unless using worktree isolation.
4. Docs-only changes (`docs/`) may be written directly by the orchestrator without spawning sub-agents.

## Sub-Agent Prompt Template

When spawning a sub-agent, the orchestrator should use this structure:

```text
PCM2WAV SUB-AGENT TASK
- Type: [feature | qa | qc | review]
- Goal: [task description]
- Scope: [exact files or directories — ONLY edit these]
- Context: [relevant background, plan references, blockers]
- Constraints:
  - Follow CLAUDE.md coding rules (§4) and architecture constraints (§5)
  - Standard library only — no external dependencies
  - Do not edit files outside scope
  - [task-specific constraints]
- Deliverable: [expected output — code changes, test files, verification results, inspection report]
```

## Verification Report Format

QC sub-agent results should follow this structure:

```text
QC VERIFICATION RESULT
- ruff check: PASS | FAIL (details)
- ruff format: PASS | FAIL (details)
- mypy: PASS | FAIL (details)
- pytest: X passed, Y failed, Z skipped
- verdict: PASS | WARN | BLOCK
- block items: (list or none)
```

Review sub-agent results should follow this structure:

```text
REVIEW INSPECTION RESULT
- CLAUDE.md compliance: PASS | WARN | BLOCK
- Architecture: PASS | WARN | BLOCK
- Security: PASS | WARN | BLOCK
- WAV format correctness: PASS | WARN | BLOCK
- Edge cases: PASS | WARN | BLOCK
- Overall verdict: PASS | WARN | BLOCK
- Block items: (list or none)
- Warn items: (list or none)
```

## Model Tier Policy

All sub-agents run on **Claude Opus 4.6 exclusively**. No lower-tier models (Sonnet, Haiku) are permitted. Do not set `model` overrides in Agent tool calls.

## Quick Start

1. Open the project root directory in VS Code or terminal.
2. Start a Claude Code session.
3. The main session acts as orchestrator — give it the goal.
4. The orchestrator reads the development plan, identifies priorities, and spawns sub-agents.
5. Results flow back to the orchestrator automatically.

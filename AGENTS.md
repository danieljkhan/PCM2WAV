# PCM2WAV AGENTS.md

This file defines the sub-agent operating model for the PCM2WAV repository.

## 1. Project Summary

- **Purpose**: PCM(Raw Audio) 파일을 WAV 파일로 변환하는 GUI 데스크탑 도구
- Target: Windows 11
- GUI: Tkinter (vista theme)
- Principle: Python 표준 라이브러리만 사용, 외부 의존성 없음

## 2. Baseline Technical Stack

- Python 3.10+
- Standard library only: `wave`, `struct`, `array`, `enum`, `tkinter`, `threading`, `queue`, `dataclasses`, `pathlib`, `json`, `logging`, `ctypes`, `time`, `sys`
- Dev tools: `ruff`, `mypy`, `pytest`

## 3. Repository Structure

```text
PCM2WAV/
  pcm2wav/
    __init__.py
    models.py
    converter.py
    presets.py
    app.py
    widgets.py
  tests/
    __init__.py
    conftest.py
    test_models.py
    test_converter.py
    test_presets.py
  docs/
    runbooks/
      weekly/
  main.py
  pyproject.toml
```

## 4. Coding Rules (Strict)

- Logging: no `print()` in production code.
- Types: all public functions/methods must have type hints.
- Docs: public functions/classes must have docstrings.
- Naming: `snake_case` (functions/vars), `PascalCase` (classes), `SCREAMING_SNAKE_CASE` (constants).
- Max line length: 100.

## 5. Architecture Constraints

- GUI layer must not contain conversion logic.
- Conversion engine must be GUI-independent — testable without Tkinter.
- Dependency direction: `app.py` → `widgets.py` → `models.py` ← `converter.py`, `models.py` ← `presets.py` (one-way).
- Circular imports prohibited.
- Thread safety: GUI updates only via `queue.Queue` + `root.after()` polling.

## 6. Sub-Agent System

The main Claude Code session (Opus 4.6) acts as **orchestrator** and spawns specialized sub-agents via the Agent tool.

### Architecture

```text
Main Claude Session (Orchestrator)
├── Sub-agent: feature    — implements converter, presets, GUI code
├── Sub-agent: qa         — writes tests for new/changed behavior
├── Sub-agent: qc         — runs lint, type checks, tests
└── Sub-agent: review     — read-only inspection (compliance, architecture, security)
```

### Sub-agent scope ownership

| Sub-agent | Owned scope | Mode |
|-----------|-------------|------|
| feature | `pcm2wav/`, `main.py`, `pyproject.toml` | write |
| qa | `tests/` | write |
| qc | (no file writes — executes commands and reports results) | execute |
| review | (entire repository, read-only) | read-only |

### Orchestrator responsibilities

- Compose sub-agent prompts with exact scope, goal, and constraints.
- Spawn independent sub-agents in parallel when scopes do not overlap.
- Use `isolation: "worktree"` when parallel sub-agents write to potentially overlapping paths.
- Collect sub-agent results and make verification decisions.
- Report progress and results to the user in Korean.

### Key rules

- Each sub-agent prompt must include explicit scope restrictions.
- Sub-agents must not expand scope beyond assignment.
- The orchestrator must not accept deliverables without the verification chain.
- Read-only sub-agents should use `subagent_type: "Explore"`.
- Writing sub-agents should use `subagent_type: "general-purpose"`.

### Mandatory verification chain — 3-round (strict)

Every deliverable (code, config, dependency changes) must pass 3 full rounds of the verification chain. The orchestrator's own review does NOT constitute verification.

**Round 1:**
1. **QA sub-agent** — writes tests for new/changed code in `tests/`.
2. **QC sub-agent** — runs `ruff check .`, `ruff format --check .`, `mypy pcm2wav/`, `pytest tests/ -v`; reports results.
3. **Review sub-agent** — read-only inspection of CLAUDE.md compliance, architecture, security; reports PASS/WARN/BLOCK.
4. **Developer fix** — orchestrator fixes all BLOCK and applicable WARN items found in Round 1.

**Round 2:**
5. **QA sub-agent** — updates/adds tests for any code changed during developer fix.
6. **QC sub-agent** — re-runs full lint/type/test suite on the fixed code.
7. **Review sub-agent** — re-inspects to confirm Round 1 issues are resolved; reports new findings.
8. **Developer fix** — orchestrator fixes any remaining BLOCK and applicable WARN items from Round 2.

**Round 3 (final):**
9. **QA sub-agent** — final test pass for any Round 2 fix changes.
10. **QC sub-agent** — final lint/type/test run. Must PASS with 0 failures.
11. **Review sub-agent** — final inspection. Must report 0 BLOCK items.
12. **Orchestrator acceptance** — may accept only if Round 3 QC and Review report no BLOCK items.

**Rules:**
- All 3 rounds are mandatory. Skipping any round is a process violation.
- Each round must complete QA → QC → Review in order before developer fix begins.
- If Round 3 Review reports BLOCK items, the cycle restarts from Round 1.
- WARN items may be deferred only if the orchestrator documents the deferral reason.

### Iterative polish loop (strict)

After the verification chain passes, the orchestrator must run an iterative polish loop on all changed files:

1. **One iteration** = review every changed file → fix issues → re-run QC.
2. **One cycle** = 10 consecutive iterations.
3. **Termination condition**: 2 consecutive 0-fix cycles (20 iterations with 0 modifications).
4. **Commit gate**: The orchestrator may only commit after the polish loop terminates. Committing before termination is a process violation.

Documentation-only or worklog-only commits (all staged files under `docs/` or `.claude/`) are exempt from both the verification chain and the polish loop.

### Sub-agent prompt templates

See `AGENT_TEAM_SETUP.md` for the sub-agent prompt template format.

## 7. Documentation and Evidence Rules

- Execution/verification logs: `docs/runbooks/`
- Weekly operation reports: `docs/runbooks/weekly/`
- Every significant change must include verification evidence.

## 8. Prohibited Actions

- Committing secrets/tokens/private keys/personal data
- Using external/third-party libraries
- Merging without test/verification evidence

## 9. Model Tier Policy

All sub-agents run on **Claude Opus 4.6 exclusively**. No lower-tier models (Sonnet, Haiku) are permitted. Do not set `model` overrides in Agent tool calls.

## 10. Language Clause for AI Outputs

- This `AGENTS.md` policy document is written in English.
- Sub-agent prompts and technical rules should remain in English for clarity.
- User-facing thought-process summaries and result reports must be output in Korean.

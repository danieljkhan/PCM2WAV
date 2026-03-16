# PCM2WAV CLAUDE.md

This file defines mandatory working standards for the PCM2WAV repository.

## 1. Project Summary

- **Purpose**: PCM(Raw Audio) 파일을 WAV 파일로 변환하는 GUI 데스크탑 도구
- Target: Windows 11
- GUI: Tkinter (vista theme)
- Principle: Python 표준 라이브러리만 사용, 외부 의존성 없음

## 2. Baseline Technical Stack

- Python 3.10+
- Standard library only: `wave`, `struct`, `array`, `enum`, `tkinter`, `threading`, `queue`, `dataclasses`, `pathlib`, `json`, `logging`, `ctypes`, `time`, `sys`
- External dependencies: None
- Dev tools: `ruff`, `mypy`, `pytest`

## 3. Repository Structure

```text
PCM2WAV/
  pcm2wav/
    __init__.py          # 패키지 초기화, __version__
    models.py            # 데이터 타입 (PcmFormat, ByteOrder, ConversionResult, PcmConversionError)
    converter.py         # 핵심 변환 로직 (PCM→WAV)
    presets.py           # 프리셋 정의 (CD, 전화, DVD 등)
    app.py               # Tkinter GUI 메인 앱
    widgets.py           # 커스텀 위젯 (ParameterPanel, FileListPanel)
  tests/
    __init__.py
    conftest.py          # 테스트 픽스처
    test_models.py       # PcmFormat 유효성 테스트
    test_converter.py    # 변환 로직 단위 테스트
    test_presets.py      # 프리셋 검증 테스트
  docs/
    runbooks/
      weekly/            # 작업일지
  main.py                # 실행 진입점
  pyproject.toml         # 프로젝트 설정 (ruff, mypy, pytest)
```

## 4. Coding Rules (Strict)

- Logging: no `print()` in production code; use structured logging where needed.
- Types: all public functions/methods must have type hints.
- Docs: public functions/classes must have docstrings.
- Naming:
  - functions/variables: `snake_case`
  - classes: `PascalCase`
  - constants: `SCREAMING_SNAKE_CASE`
- Max line length: 100.

## 5. Architecture Constraints

- GUI layer (`app.py`, `widgets.py`) must not contain conversion logic.
- Conversion engine (`converter.py`) must be fully independent of GUI — testable without Tkinter.
- Dependency direction: `app.py` → `widgets.py` → `models.py` ← `converter.py`, `models.py` ← `presets.py` (one-way).
- Circular imports are prohibited.
- Thread safety: GUI updates only via `queue.Queue` + `root.after()` polling, never direct cross-thread Tkinter calls.

## 6. Git and Branch Policy (Strict)

Mandatory rules:

1. Every change must follow the delivery pipeline before commit.
2. PR checks must pass:
   - `ruff check .`
   - `ruff format --check .`
   - `mypy pcm2wav/`
   - `pytest tests/ -v`
3. Commit messages must use category prefixes:
   - `[feature]`, `[fix]`, `[docs]`, `[test]`, `[chore]`

## 7. Sub-Agent System

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

- Composing sub-agent prompts with exact scope, goal, and constraints.
- Spawning independent sub-agents in parallel when scopes do not overlap.
- Using `isolation: "worktree"` when parallel sub-agents write to potentially overlapping paths.
- Collecting sub-agent results and making verification decisions.
- Reporting progress and results to the user in Korean.

### Key rules

- Each sub-agent prompt must include explicit scope restrictions.
- Sub-agents must not expand scope beyond assignment.
- The orchestrator must not accept deliverables without the verification chain.
- Read-only sub-agents should use `subagent_type: "Explore"`.
- Writing sub-agents should use `subagent_type: "general-purpose"`.

### Mandatory delivery pipeline (strict)

The complete delivery pipeline for any technical change is:

1. **Implementation** — sub-agents write code within assigned scope.
2. **Verification chain (3-round)** — 3 rounds of QA → QC → Review with developer fixes between rounds.
3. **Iterative polish loop** — runs on all changed files until termination condition is met.
4. **Commit** — only after the polish loop terminates with 0 fixes.

No step may be skipped. Committing before the polish loop terminates is a process violation.

### Mandatory verification chain — 3-round (strict)

Every deliverable (code, config, dependency changes) must pass 3 full rounds of the verification chain. The orchestrator's own review does NOT constitute verification.

**Round 1:**
1. **QA sub-agent** — writes tests for new/changed code in `tests/`.
2. **QC sub-agent** — runs `ruff check .`, `ruff format --check .`, `mypy pcm2wav/`, `pytest tests/ -v`; reports results.
3. **Review sub-agent** — independent read-only inspection; reports PASS/WARN/BLOCK findings.
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

The iterative polish loop **must** run after every commit that includes technical changes (code, config, dependency). Documentation-only or worklog-only commits (all staged files under `docs/` or `.claude/`) are exempt from both the verification chain and the polish loop.

After the verification chain passes, the orchestrator must run an iterative polish loop on all changed files:

1. **One iteration** = review every changed file → identify issues (lint, type errors, logic bugs, style, missing tests, docstring gaps, CLAUDE.md violations) → fix all found issues → re-run QC (`ruff check .`, `ruff format --check .`, `mypy pcm2wav/`, `pytest tests/ -v`).
2. **One cycle** = 10 consecutive iterations.
3. Repeat cycles until the **termination condition** is met.
4. **Termination condition**: **2 consecutive 0-fix cycles** (i.e. 20 consecutive iterations with zero modifications). The loop terminates and the change is ready to commit.
5. Each iteration must log its modification count. The orchestrator reports the cumulative count per cycle to the user.
6. **Commit gate**: The orchestrator may only commit after the polish loop terminates. Committing before termination is a process violation.

## 8. Documentation and Evidence Rules

- Execution/verification logs: `docs/runbooks/`
- Weekly operation reports: `docs/runbooks/weekly/`
- **Post-commit automatic worklog update (strict)**:
  - Every successful commit triggers `post_commit_worklog.py` (PostToolUse hook).
  - The orchestrator **must** update the worklog **immediately and automatically** — before responding to the user.
  - If a worklog for the day exists in `docs/runbooks/weekly/`, append/update the commit entry.
  - If no worklog exists, create one named `YYYY-MM-DD-<topic>-worklog.md`.
  - Required fields per commit entry: commit hash, change summary, verification results, remaining tasks, update timestamp (KST, `YYYY-MM-DD HH:MM KST`).
  - This is not a reminder — it is a mandatory auto-action. Skipping is a process violation.

## 9. Hook System Prerequisites

- The `.claude/settings.json` hook commands use bare `python` to invoke hook scripts.
- This requires `python` (3.10+) to be on the system PATH.
- Hook scripts use only the standard library — any Python 3.10+ interpreter works.

## 10. Prohibited Actions

- Committing secrets/tokens/private keys/personal data
- Using external/third-party libraries (standard library only)
- Merging without test/verification evidence
- Direct cross-thread Tkinter calls (must use queue polling)

## 11. Model Tier Policy

All sub-agents run on **Claude Opus 4.6 exclusively**. No lower-tier models (Sonnet, Haiku) are permitted for any sub-agent task.

- The orchestrator session itself runs on Opus 4.6.
- Every sub-agent spawned via the Agent tool inherits Opus 4.6. Do not set `model: "sonnet"` or `model: "haiku"` overrides.

## 12. Language Clause for AI Outputs

- This `CLAUDE.md` policy document is written in English.
- Agent-facing planning and technical rules should remain in English for clarity.
- User-facing thought-process summaries and result reports must be output in Korean.

# Skills Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove legacy references and deprecated skills, and align remaining skills with current scripts and best agent-skill practices.

**Architecture:** Inline all critical runbook content into each SKILL.md, remove `references` symlink and skill-level `references/` folders, and standardize skill frontmatter + quick commands. Enforce via a lightweight guard test.

**Tech Stack:** Python (pytest), Markdown (SKILL.md), Git submodules (`skills`).

---

### Task 1: Add guard test for legacy references (RED)

**Files:**
- Create: `tests/skills/test_no_legacy_references.py`

**Step 1: Write the failing test**

```python
from __future__ import annotations

from pathlib import Path


def test_no_legacy_references_symlink_or_dirs():
    root = Path(__file__).resolve().parents[2]
    assert not (root / "references").exists()

    skills = root / "skills"
    if not skills.exists():
        return
    bad = [p for p in skills.rglob("references") if p.is_dir()]
    assert not bad
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/skills/test_no_legacy_references.py -q`
Expected: FAIL because `references` exists and skill `references/` folders still exist.

---

### Task 2: Remove deprecated skills + legacy references (GREEN)

**Files:**
- Delete: `skills/csv-data-summarizer-claude-skill/`
- Delete: `skills/software-architecture/`
- Delete: `references` (root symlink)
- Delete: `skills/*/references/` (all remaining)

**Step 1: Remove directories**

Commands:
- `git -C skills rm -r csv-data-summarizer-claude-skill software-architecture`
- `git -C skills rm -r market-ops/references telegram-ingest-ops/references token-on-demand/references`
- `rm -f references`

**Step 2: Re-run test**

Run: `PYTHONPATH=. pytest tests/skills/test_no_legacy_references.py -q`
Expected: PASS

**Step 3: Commit (skills submodule)**

```bash
git -C skills add -A
git -C skills commit -m "chore: remove deprecated skills and references"
```

---

### Task 3: Rewrite remaining skills inline (RED)

**Files:**
- Modify: `skills/market-ops/SKILL.md`
- Modify: `skills/token-on-demand/SKILL.md`
- Modify: `skills/telegram-ingest-ops/SKILL.md`
- Modify: `skills/hummingbot-mcp-ops/SKILL.md`

**Step 1: Write failing test (content check)**

Add assertions to the guard test to ensure:
- Frontmatter has only `name` + `description`
- `description` starts with `Use when...`
- No `references/` strings remain in skills

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/skills/test_no_legacy_references.py -q`
Expected: FAIL until SKILL.md updated.

---

### Task 4: Update skill content to best practice (GREEN)

**Files:**
- Modify the four SKILL.md files to:
  - Inline core runbook content
  - Keep under ~200–300 words where possible
  - Replace all `references/*` mentions with inline sections
  - Update commands to match current `scripts` structure
  - Ensure output boundaries and error handling are explicit

**Step 1: Apply edits (minimal but complete)**

**Step 2: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/skills/test_no_legacy_references.py -q`
Expected: PASS

**Step 3: Commit (skills submodule)**

```bash
git -C skills add -A
git -C skills commit -m "docs: refresh core ops skills"
```

---

### Task 5: Bump submodule + finalize

**Files:**
- Modify: `skills` (submodule pointer)

**Step 1: Update main repo pointer**

```bash
git add skills
git commit -m "chore: update skills submodule"
```

**Step 2: Push**

```bash
git -C skills push origin HEAD:main
git push
```

**Step 3: Full check (optional)**

Run: `PYTHONPATH=. pytest tests/skills/test_no_legacy_references.py -q`
Expected: PASS

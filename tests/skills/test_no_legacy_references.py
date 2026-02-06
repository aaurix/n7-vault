from __future__ import annotations

from pathlib import Path


def _parse_frontmatter_keys(text: str) -> list[str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    keys: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key = line.split(":", 1)[0].strip()
        if key:
            keys.append(key)
    return keys


def _parse_frontmatter_description(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.strip().startswith("description:"):
            value = line.split(":", 1)[1].strip()
            return value.strip("'\"")
    return ""


def test_no_legacy_references_symlink_or_dirs():
    root = Path(__file__).resolve().parents[2]
    assert not (root / "references").exists()

    skills = root / "skills"
    if not skills.exists():
        return
    bad = [p for p in skills.rglob("references") if p.is_dir()]
    assert not bad

    skill_files = list(skills.rglob("SKILL.md"))
    for skill_path in skill_files:
        text = skill_path.read_text(encoding="utf-8")
        assert "references/" not in text
        keys = _parse_frontmatter_keys(text)
        assert keys, f"missing frontmatter in {skill_path}"
        assert set(keys) <= {"name", "description"}, f"extra frontmatter keys in {skill_path}"
        desc = _parse_frontmatter_description(text)
        assert desc.startswith("Use when"), f"description must start with 'Use when' in {skill_path}"

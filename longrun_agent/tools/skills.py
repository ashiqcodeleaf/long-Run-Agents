"""Skill discovery and import helpers."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from longrun_agent.config import ensure_home, get_longrun_home


def bundled_skills_dir() -> Path:
    """Return the project-bundled skills directory."""

    return Path(__file__).resolve().parents[2] / "skills"


def home_skills_dir() -> Path:
    """Return the user's LongRun skills directory."""

    ensure_home()
    return get_longrun_home() / "skills"


def list_skills(*, source: str = "all") -> list[dict[str, str]]:
    """List skills from bundled and/or home directories."""

    rows: list[dict[str, str]] = []
    if source in {"all", "bundled"}:
        rows.extend(_list_skills_in_dir(bundled_skills_dir(), source="bundled"))
    if source in {"all", "home"}:
        rows.extend(_list_skills_in_dir(home_skills_dir(), source="home"))
    return sorted(rows, key=lambda row: (row["name"], row["source"]))


def read_skill(name: str, *, source: str = "bundled") -> dict[str, str]:
    """Read a skill by name from the requested source."""

    if source not in {"bundled", "home"}:
        raise ValueError("source must be bundled or home")
    root = bundled_skills_dir() if source == "bundled" else home_skills_dir()
    matches = [skill for skill in _list_skills_in_dir(root, source=source) if skill["name"] == name]
    if not matches:
        raise FileNotFoundError(f"Skill not found: {name}")
    path = Path(matches[0]["path"])
    return {
        "name": name,
        "source": source,
        "path": str(path),
        "content": path.read_text(encoding="utf-8", errors="replace"),
    }


def read_skill_any_source(name: str) -> dict[str, str]:
    """Read a skill, preferring home skills over bundled skills."""

    for source in ("home", "bundled"):
        try:
            return read_skill(name, source=source)
        except FileNotFoundError:
            continue
    raise FileNotFoundError(f"Skill not found: {name}")


def build_skill_user_message(name: str, task: str) -> str:
    """Return a prompt-cache-safe user message for a skill command."""

    skill = read_skill_any_source(name)
    clean_task = task.strip() or "Use this skill for the current request."
    return (
        f"Use the `{skill['name']}` skill for this request.\n\n"
        f"Skill source: {skill['source']}\n"
        f"Skill path: {skill['path']}\n\n"
        "Read and follow the full SKILL.md content below for this user turn. "
        "This is user-turn context, not a system prompt mutation.\n\n"
        "----- SKILL.md -----\n"
        f"{skill['content'].strip()}\n"
        "----- END SKILL.md -----\n\n"
        f"User task:\n{clean_task}"
    )


def skills_list_tool(category: str | None = None) -> dict[str, Any]:
    """Return metadata for available skills without loading full contents."""

    skills = list_skills(source="all")
    rows: list[dict[str, str]] = []
    for skill in skills:
        path = Path(skill["path"])
        skill_category = path.parent.parent.name if path.parent.name else "skills"
        if category and skill_category != category:
            continue
        description = _skill_description(path)
        rows.append(
            {
                "name": skill["name"],
                "source": skill["source"],
                "category": skill_category,
                "description": description,
                "path": skill["path"],
            }
        )
    return {
        "skills": rows,
        "count": len(rows),
        "categories": sorted({row["category"] for row in rows}),
    }


def skill_view_tool(name: str, file_path: str | None = None) -> dict[str, Any]:
    """Load one skill's SKILL.md or a linked file inside that skill directory."""

    skill = read_skill_any_source(name)
    skill_dir = Path(skill["path"]).parent.resolve()
    if file_path:
        target = (skill_dir / file_path).resolve()
        if not str(target).startswith(str(skill_dir)):
            raise ValueError("file_path must stay inside the skill directory")
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"Skill linked file not found: {file_path}")
        return {
            "name": skill["name"],
            "file": file_path,
            "path": str(target),
            "content": target.read_text(encoding="utf-8", errors="replace"),
        }
    linked_files = _linked_files(skill_dir)
    return {
        "name": skill["name"],
        "source": skill["source"],
        "path": skill["path"],
        "description": _skill_description(Path(skill["path"])),
        "content": skill["content"],
        "linked_files": linked_files,
        "usage_hint": "Call skill_view with file_path to read linked files." if linked_files else None,
    }


def import_bundled_skills(*, overwrite: bool = False) -> dict[str, Any]:
    """Copy bundled skills into the LongRun home skills directory."""

    source = bundled_skills_dir()
    target = home_skills_dir()
    if not source.exists():
        raise FileNotFoundError(f"Bundled skills directory not found: {source}")

    copied = 0
    skipped = 0
    for item in source.iterdir():
        destination = target / item.name
        if destination.exists():
            if not overwrite:
                skipped += 1
                continue
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)
        copied += 1

    return {
        "source": str(source),
        "target": str(target),
        "copied": copied,
        "skipped": skipped,
    }


def _list_skills_in_dir(root: Path, *, source: str) -> list[dict[str, str]]:
    if not root.exists():
        return []
    rows: list[dict[str, str]] = []
    for skill_file in root.rglob("SKILL.md"):
        name = skill_file.parent.name
        rows.append(
            {
                "name": name,
                "source": source,
                "path": str(skill_file),
            }
        )
    return rows


def _skill_description(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines()[:40]:
        stripped = line.strip()
        if stripped.startswith("description:"):
            return stripped.split(":", 1)[1].strip().strip("\"'")
    return ""


def _linked_files(skill_dir: Path) -> dict[str, list[str]]:
    groups = {"references": [], "templates": [], "assets": [], "scripts": [], "other": []}
    for path in skill_dir.rglob("*"):
        if not path.is_file() or path.name == "SKILL.md":
            continue
        rel = str(path.relative_to(skill_dir)).replace("\\", "/")
        if rel.startswith("references/"):
            groups["references"].append(rel)
        elif rel.startswith("templates/"):
            groups["templates"].append(rel)
        elif rel.startswith("assets/"):
            groups["assets"].append(rel)
        elif rel.startswith("scripts/"):
            groups["scripts"].append(rel)
        else:
            groups["other"].append(rel)
    return {key: sorted(value) for key, value in groups.items() if value}


def register_skill_tools(registry: Any) -> None:
    try:
        registry.register(
            name="skills_list",
            description="List available skills with metadata only. Use skill_view to load full instructions.",
            toolset="skills",
            parameters={
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                },
                "required": [],
                "additionalProperties": False,
            },
            handler=lambda args: skills_list_tool(args.get("category")),
        )
    except ValueError as exc:
        if "already registered" not in str(exc):
            raise
    try:
        registry.register(
            name="skill_view",
            description="Load a skill's full SKILL.md content or one linked file inside that skill.",
            toolset="skills",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "file_path": {"type": "string"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
            handler=lambda args: skill_view_tool(str(args.get("name", "")), args.get("file_path")),
        )
    except ValueError as exc:
        if "already registered" not in str(exc):
            raise

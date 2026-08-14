"""Enumerate Claude Code skills installed under ~/.claude/skills/.

Mirrors the same TEAM vs PERSONAL classification logic as the `/flows-list`
team skill (see `team-skills/flows-list/SKILL.md`):

  - An entry whose realpath ends in `team-skills/<name>` is TEAM (symlink into
    the BrowserMCP repo created by `team-onboarding/scripts/install.sh`).
  - Anything else (a plain directory created by `/save-as-flow`,
    `/create-flow`, or the user's own hand) is PERSONAL.

Each entry parses the leading YAML frontmatter of SKILL.md to pull `name`,
`description`, and (best-effort) `arguments`. The body of SKILL.md is also
returned so the Skills page can render the full file in a drilldown without
re-reading the disk.

`last_run` is filled in by joining against the most recent run log whose
`skill` field matches the skill name. We delegate the heavy lifting to
`load_recent_runs()` so we touch each JSONL file at most once per render.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .runs import load_recent_runs

SKILLS_DIR = Path(os.path.expanduser("~/.claude/skills"))
TEAM_MARKER = "team-skills"  # path segment that identifies a team-skill symlink


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a SKILL.md into (frontmatter_dict, body).

    Hand-rolled instead of importing PyYAML — frontmatter here is intentionally
    flat (name, description, plus an optional list of `arguments`), and we don't
    want to add a dependency for the Streamlit extra.

    Returns ({}, original_text) if the file has no frontmatter block.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}, text

    fm_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1 :]).lstrip("\n")

    # Tiny YAML-ish parser: top-level `key: value` pairs, plus a single
    # nested list under `arguments:` where each item starts with `- name:`.
    meta: dict[str, Any] = {}
    args: list[dict[str, Any]] = []
    in_args = False
    current_arg: dict[str, Any] | None = None
    for raw in fm_lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and not line.startswith("\t"):
            in_args = False
            current_arg = None
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key == "arguments":
                    in_args = True
                    meta["arguments"] = args
                else:
                    meta[key] = value
        elif in_args:
            stripped = line.strip()
            if stripped.startswith("- "):
                current_arg = {}
                args.append(current_arg)
                # support inline `- name: foo`
                inner = stripped[2:]
                if ":" in inner:
                    k, _, v = inner.partition(":")
                    current_arg[k.strip()] = v.strip().strip('"').strip("'")
            elif current_arg is not None and ":" in stripped:
                k, _, v = stripped.partition(":")
                current_arg[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body


def _classify(entry: Path) -> str:
    """Return "team" if `entry` is a symlink into team-skills/, else "personal"."""
    if entry.is_symlink():
        resolved = entry.resolve()
        parts = resolved.parts
        # Look for `.../team-skills/<name>` shape.
        if TEAM_MARKER in parts:
            idx = parts.index(TEAM_MARKER)
            if idx < len(parts) - 1:  # has a name segment after team-skills
                return "team"
    return "personal"


def _read_skill(entry: Path) -> dict[str, Any] | None:
    """Read SKILL.md for one skill directory. Returns None if unreadable."""
    skill_md = entry / "SKILL.md"
    if not skill_md.exists():
        return None
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    meta, body = _parse_frontmatter(text)
    name = meta.get("name") or entry.name
    description = meta.get("description") or "(no description)"
    arguments = meta.get("arguments") if isinstance(meta.get("arguments"), list) else []
    return {
        "name": name,
        "description": description,
        "arguments": arguments,
        "path": str(skill_md),
        "body": body,
        "frontmatter": meta,
    }


def list_skills_classified() -> dict[str, list[dict[str, Any]]]:
    """Return {"team": [...], "personal": [...]} of all installed skills.

    Each entry is a dict with keys:
      name (str), description (str), arguments (list), path (str),
      body (str), frontmatter (dict), last_run (str | None),
      last_run_status (str | None — "ok" | "error" | None).

    Entries that fail to parse (no SKILL.md, unreadable, etc.) are silently
    skipped — the dashboard is a glance, not a forensic tool.
    """
    out: dict[str, list[dict[str, Any]]] = {"team": [], "personal": []}
    if not SKILLS_DIR.exists():
        return out

    # Pre-index the most recent run per skill name so we don't re-scan logs
    # once per skill. `load_recent_runs` already caps at 100 newest, which is
    # plenty to find a "last run" for currently-active skills.
    last_run_by_skill: dict[str, dict[str, Any]] = {}
    for run in load_recent_runs(limit=100, since_days=30):
        skill = run.get("skill")
        if skill and skill not in last_run_by_skill:
            last_run_by_skill[skill] = run

    for entry in sorted(SKILLS_DIR.iterdir(), key=lambda p: p.name.lower()):
        # Skip hidden files like .DS_Store on macOS.
        if entry.name.startswith("."):
            continue
        if not entry.is_dir() and not entry.is_symlink():
            continue
        info = _read_skill(entry)
        if info is None:
            continue
        bucket = _classify(entry)
        last = last_run_by_skill.get(info["name"])
        info["last_run"] = last["timestamp"] if last else None
        info["last_run_status"] = last["status"] if last else None
        info["source"] = "TEAM" if bucket == "team" else "PERSONAL"
        out[bucket].append(info)
    return out

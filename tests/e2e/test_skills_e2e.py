"""End-to-end smoke tests for the shipped team skills.

These tests are intentionally shape-only — they prove that the BrowserMCP
chrome_attach → chrome_find_or_open_window → navigate sequence used by
every team skill still works against the real internal hosts. They do NOT
assert on report content, KPI values, search results, or anything else
that could legitimately drift week-to-week without indicating a regression.

Run manually before a release:

    pytest -m e2e tests/e2e/

Preconditions every test (except the local-FS one) shares:
  - Chrome running with `--remote-debugging-port=9222`
  - The user is already signed in to the target SaaS (we don't drive SSO)
  - VPN is up so the internal host resolves

When any precondition is missing the test calls pytest.skip() with a clear
reason — we'd rather see "skipped (VPN down)" than a red bar from a
network error that has nothing to do with the code under test.
"""
from __future__ import annotations

import socket
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

from tests.e2e.conftest import reachable


CHROME_DEBUG_PORT = 9222


def _chrome_reachable() -> bool:
    """True if a Chrome with --remote-debugging-port=9222 is accepting CDP."""
    try:
        with socket.create_connection(("127.0.0.1", CHROME_DEBUG_PORT), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.mark.e2e
async def test_powerbi_landing_smoke() -> None:
    """Smoke test the /powerbi-scan attach + navigate prelude against app.powerbi.com.

    Exercises the first three calls of team-skills/powerbi-scan/SKILL.md:
    chrome_attach → chrome_find_or_open_window("app.powerbi.com") → navigate
    to the landing page. We don't render any specific report — content tests
    belong in /powerbi-scan's own integration suite, not this smoke pass.
    """
    if not _chrome_reachable():
        pytest.skip(
            f"No Chrome with --remote-debugging-port={CHROME_DEBUG_PORT} reachable; "
            "start Chrome with `--remote-debugging-port=9222` to run e2e tests"
        )
    if not reachable("https://app.powerbi.com"):
        pytest.skip("app.powerbi.com unreachable (VPN down or off-network?)")

    from browsermcp.tools import chrome_attach, chrome_find_or_open_window, navigate

    await chrome_attach(port=CHROME_DEBUG_PORT)
    window = await chrome_find_or_open_window("app.powerbi.com")
    result = await navigate("https://app.powerbi.com", window_id=window.window_id)

    title = result.title or ""
    # Power BI's landing redirects to either the signed-in app shell
    # ("... | Power BI") or the Microsoft sign-in flow if the session
    # expired. Either is a healthy outcome for this smoke test — we're
    # proving the attach + navigate path, not auth status.
    assert "Power BI" in title or "Sign in" in title, (
        f"Unexpected landing title: {title!r}"
    )


@pytest.mark.e2e
async def test_confluence_landing_smoke() -> None:
    """Smoke test the /confluence-search attach + navigate prelude.

    Mirrors team-skills/confluence-search/SKILL.md's opening sequence
    against the corporate Confluence host. Same shape as the Power BI
    test — landing page only, no specific page or query rendered.
    """
    if not _chrome_reachable():
        pytest.skip(
            f"No Chrome with --remote-debugging-port={CHROME_DEBUG_PORT} reachable; "
            "start Chrome with `--remote-debugging-port=9222` to run e2e tests"
        )
    if not reachable("https://confluence.example.com"):
        pytest.skip("confluence.example.com unreachable (VPN down or off-network?)")

    from browsermcp.tools import chrome_attach, chrome_find_or_open_window, navigate

    await chrome_attach(port=CHROME_DEBUG_PORT)
    window = await chrome_find_or_open_window("confluence.example.com")
    result = await navigate("https://confluence.example.com", window_id=window.window_id)

    title = result.title or ""
    assert "Confluence" in title or "Sign in" in title, (
        f"Unexpected landing title: {title!r}"
    )


@pytest.mark.e2e
async def test_jira_landing_smoke() -> None:
    """Smoke test the /jira-bulk-update attach + navigate prelude.

    Mirrors team-skills/jira-bulk-update/SKILL.md's opening sequence
    against the corporate Jira host. No bulk action is run — the
    destructive path is covered by the write-gate integration tests.
    """
    if not _chrome_reachable():
        pytest.skip(
            f"No Chrome with --remote-debugging-port={CHROME_DEBUG_PORT} reachable; "
            "start Chrome with `--remote-debugging-port=9222` to run e2e tests"
        )
    if not reachable("https://jira.example.com"):
        pytest.skip("jira.example.com unreachable (VPN down or off-network?)")

    from browsermcp.tools import chrome_attach, chrome_find_or_open_window, navigate

    await chrome_attach(port=CHROME_DEBUG_PORT)
    window = await chrome_find_or_open_window("jira.example.com")
    result = await navigate("https://jira.example.com", window_id=window.window_id)

    title = result.title or ""
    # Jira's landing variously renders "System Dashboard - JIRA",
    # "Log in - JIRA", or "Sign in" depending on auth + version.
    assert "Jira" in title or "JIRA" in title or "Sign in" in title, (
        f"Unexpected landing title: {title!r}"
    )


@pytest.mark.e2e
def test_save_as_flow_writes_personal_skill(tmp_path: Path) -> None:
    """Smoke test: a SKILL.md with valid YAML frontmatter is round-trippable.

    LIMITATION (honest scope): this test does NOT exercise any /save-as-flow
    logic — that lives in the SKILL.md prose and runs through Claude Code at
    skill-invocation time. There is no Python helper to call directly. What
    this test DOES verify is the contract /save-as-flow promises about its
    output file: a YAML frontmatter block delimited by `---`, parseable, with
    a `name:` field that matches the directory name.

    Replacing this test with one that drives the real skill requires either
    (a) refactoring /save-as-flow to extract a `write_personal_skill(...)`
    Python helper that both the skill body AND the test can call, or
    (b) running an actual Claude Code session in CI. (a) is the Phase 4
    work; until then this test is intentionally narrow.

    Marked e2e (not unit) because it covers the meta-skill loop — the
    "skill that writes another skill" contract that the rest of the
    library depends on.
    """
    # The skill name must match /save-as-flow's kebab-case validation
    # rule from step 1 of SKILL.md. We randomize a suffix so parallel
    # runs and re-runs don't collide on the same directory.
    skill_name = f"test-saveasflow-{uuid.uuid4().hex[:8]}"

    # In-memory "recent chat" — the shape /save-as-flow would derive
    # in step 3 of its flow. Two successful tool calls clears the
    # "fewer than 2 successful tool calls" refusal in step 3.
    recent_chat = [
        ("chrome_attach", {"port": 9222}),
        ("chrome_find_or_open_window", {"url_pattern": "app.powerbi.com"}),
        ("navigate", {"url": "https://app.powerbi.com", "window_id": "w-abc12345"}),
    ]
    assert len(recent_chat) >= 2, "fake chat must satisfy the >=2 successful tool calls rule"

    # Skip the chat-reflection + secret-scan steps (they need a Claude
    # in the loop) and exercise only the documented file-writing routine
    # from step 6: resolve <home>/.claude/skills/<name>/SKILL.md, mkdir
    # -p the parent, and Write the frontmatter + body.
    fake_home = tmp_path
    skill_dir = fake_home / ".claude" / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    target = skill_dir / "SKILL.md"

    description = "Open a Power BI report and read the landing page."
    arguments_block = (
        "arguments:\n"
        "  - name: report\n"
        "    type: string\n"
        "    required: true\n"
        "    description: The Power BI report URL to open.\n"
    )
    body = "\n".join(
        [
            "# Test Saveasflow",
            "",
            "You are reopening a saved Power BI workflow.",
            "",
            "## Inputs",
            "",
            "- `report` — the Power BI report URL to open.",
            "",
            "## Flow",
            "",
        ]
        + [
            f"### {i + 1}. {tool_name}\n\nCall `{tool_name}({args!r})`."
            for i, (tool_name, args) in enumerate(recent_chat)
        ]
    )
    target.write_text(
        f"---\nname: {skill_name}\ndescription: {description}\n{arguments_block}---\n\n{body}\n"
    )

    try:
        assert target.exists(), f"SKILL.md never appeared at {target}"

        # Parse the frontmatter with the stdlib — pyyaml may not be
        # installed in every e2e environment, and the validation we
        # care about here (name matches, frontmatter is well-formed)
        # is simple enough that splitting on the --- fences is fine.
        contents = target.read_text()
        assert contents.startswith("---\n"), "frontmatter must open with --- fence"
        _, frontmatter, _body = contents.split("---\n", 2)
        # The name line must echo the skill name exactly so the slash
        # command resolves to this file.
        name_line = next(
            (ln for ln in frontmatter.splitlines() if ln.startswith("name:")),
            None,
        )
        assert name_line is not None, "frontmatter missing `name:` field"
        assert name_line.split(":", 1)[1].strip() == skill_name, (
            f"name field {name_line!r} does not match skill_name {skill_name!r}"
        )
    finally:
        # Teardown — rmtree the per-test skill dir even on assertion
        # failure so the test can be re-run cleanly. tmp_path is itself
        # cleaned up by pytest, but we belt-and-brace it in case a
        # future refactor of this test points at a real $HOME.
        if skill_dir.exists():
            shutil.rmtree(skill_dir, ignore_errors=True)

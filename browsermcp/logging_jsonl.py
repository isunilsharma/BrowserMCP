import contextlib
import json
import uuid
from datetime import datetime, timezone

from . import _context
from .config import RUNS_DIR, ensure_dirs
from .redact import SENSITIVE_FIELD_RE, _redact_str, redact


def _sanitize_tool_args(tool: str, args):
    """Apply per-tool argument sanitization before the generic redact() pass."""
    if tool == "type_text" and isinstance(args, dict):
        field_value = args.get("field")
        if isinstance(field_value, str) and SENSITIVE_FIELD_RE.search(field_value):
            args = dict(args)
            if "text" in args:
                args["text"] = "<redacted-typed-input>"
    return args


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@contextlib.contextmanager
def run_logger(skill: str | None = None):
    """Yield a logging callable that appends JSONL events for a single run.

    If `skill` is provided, it overrides whatever is in the module-level
    context. If omitted (the typical case from the server wrapper), each log
    line reads the current skill from `browsermcp._context.get_current_skill()`
    at log time — so a skill that called `set_skill_context` first will have
    every subsequent tool call attributed to it.
    """
    ensure_dirs()
    run_id = f"r-{uuid.uuid4().hex[:8]}"
    path = RUNS_DIR / f"{run_id}.jsonl"

    def log(tool, args, result, duration_ms):
        sanitized_args = _sanitize_tool_args(tool, args)
        current_skill = skill if skill is not None else _context.get_current_skill()
        line = {
            "t": _utc_iso_now(),
            "run_id": run_id,
            "skill": current_skill,
            "tool": tool,
            "args": redact(sanitized_args),
            "result_summary": _redact_str(str(result))[:200],
            "duration_ms": duration_ms,
        }
        with path.open("a") as fh:
            fh.write(json.dumps(line) + "\n")

    yield log

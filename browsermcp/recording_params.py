"""Phase 4 v0.1 parameterization heuristics for /record-flow.

Given a recording's events, identify values that should become {{params}}:
- URLs in navigate events (always candidate)
- Search query / input strings (if a small set of common patterns)
- Dates (YYYY-MM-DD, MM/DD/YYYY)
- IDs that look like ticket numbers (ABC-1234, INC#######)
"""

from __future__ import annotations
import re
from collections import Counter
from pydantic import BaseModel


_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b")
_TICKET_RE = re.compile(r"\b([A-Z]{2,6}-\d{3,7}|INC\d{6,})\b")
_URL_RE = re.compile(r"https?://[^\s\"<>]+", re.IGNORECASE)


class Parameter(BaseModel):
    name: str           # kebab-case argname
    default: str        # captured value
    occurrences: list[int]  # event indices where it appears


def extract_parameters(events: list[dict]) -> list[Parameter]:
    """Inspect events and return a list of suggested parameters.

    Heuristics:
    - The FIRST navigate event's URL becomes {{start-url}} (typical starting URL).
    - Any date string seen in an input value becomes {{date}}.
    - Any ticket ID in an input or URL becomes {{ticket}}.
    - Any input value that appears in 2+ events becomes {{<field-name>}}.
    """
    params: list[Parameter] = []
    seen_values: Counter[str] = Counter()

    # First navigate event = start-url
    for i, ev in enumerate(events):
        if ev.get("kind") == "navigate" and ev.get("url"):
            params.append(Parameter(
                name="start-url",
                default=ev["url"],
                occurrences=[i],
            ))
            break

    for i, ev in enumerate(events):
        if ev.get("kind") != "input":
            continue
        value = (ev.get("value") or "").strip()
        if not value or value == "<password-redacted>":
            continue
        seen_values[value] += 1

        # Date pattern
        if _DATE_RE.search(value):
            if not any(p.name == "date" for p in params):
                params.append(Parameter(
                    name="date", default=value, occurrences=[i],
                ))
            else:
                next(p for p in params if p.name == "date").occurrences.append(i)

        # Ticket pattern
        if _TICKET_RE.search(value):
            if not any(p.name == "ticket" for p in params):
                params.append(Parameter(
                    name="ticket", default=value, occurrences=[i],
                ))
            else:
                next(p for p in params if p.name == "ticket").occurrences.append(i)

    # Inputs whose value appears 2+ times — promote to a parameter named after
    # the field (kebab-cased).
    for value, count in seen_values.items():
        if count < 2:
            continue
        # Find the first input event with this value
        for i, ev in enumerate(events):
            if ev.get("kind") == "input" and ev.get("value") == value:
                field = (ev.get("field") or "value").strip().lower()
                argname = re.sub(r"[^a-z0-9-]+", "-", field).strip("-")[:30] or "value"
                if not any(p.name == argname for p in params):
                    params.append(Parameter(
                        name=argname, default=value,
                        occurrences=[j for j, e in enumerate(events)
                                     if e.get("kind") == "input" and e.get("value") == value],
                    ))
                break

    # Cap at 5 parameters — beyond that the skill is too noisy.
    return params[:5]

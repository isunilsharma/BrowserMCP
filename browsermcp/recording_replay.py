"""Phase 4 v0.2 replay engine for /record-flow — Option C multi-tab.

Walks a saved recording's events in order. Each event carries an optional
`window_id` field (set by the Option C recorder). The replay engine opens one
window per distinct window_id it encounters, keeping a mapping from recorded
window_id → live replay window_id. For recordings made with the old single-tab
path (no window_id on events), all events are replayed in the caller-supplied
fallback window_id.

Self-healing: click() already uses browser_use's LLM/DOM fuzzy resolver, so
stale text labels are handled automatically.
"""

from __future__ import annotations

from pydantic import BaseModel

from .recorder import Recording, load_recording


class ReplayStep(BaseModel):
    index: int
    kind: str           # "click" | "input" | "navigate" | "skipped"
    ok: bool
    window_id: str | None = None
    notes: str | None = None


async def replay_recording(name: str, window_id: str) -> list[dict]:
    """Replay a recording. `window_id` is used as the fallback for events
    that have no window_id (old single-tab recordings)."""
    from .tools.navigation import navigate, wait_for
    from .tools.interaction import click, type_text
    from .tools.chrome import chrome_find_or_open_window

    rec: Recording = load_recording(name)
    results: list[ReplayStep] = []

    # Map from recorded window_id → live replay window_id.
    # The fallback (caller-supplied) window_id handles old recordings.
    wid_map: dict[str, str] = {}

    async def _resolve_window(recorded_wid: str | None) -> str:
        """Return the live window_id for a recorded window_id."""
        if not recorded_wid:
            return window_id  # single-tab fallback
        if recorded_wid in wid_map:
            return wid_map[recorded_wid]
        # First time we see this recorded window — open a fresh tab for it.
        result = await chrome_find_or_open_window(url_pattern="*")
        live_wid = result["window_id"] if isinstance(result, dict) else str(result)
        wid_map[recorded_wid] = live_wid
        return live_wid

    for i, ev in enumerate(rec.events):
        kind = ev.kind
        rec_wid = ev.window_id  # may be None for old recordings
        try:
            live_wid = await _resolve_window(rec_wid)

            if kind == "navigate":
                if not ev.url:
                    results.append(ReplayStep(index=i, kind=kind, ok=False,
                                              window_id=live_wid,
                                              notes="event has no url"))
                    continue
                await navigate(url=ev.url, window_id=live_wid)
                await wait_for(condition="page finishes loading",
                               timeout_s=20, window_id=live_wid)
                results.append(ReplayStep(index=i, kind="navigate", ok=True,
                                          window_id=live_wid, notes=ev.url))

            elif kind == "click":
                desc = ev.description or "<unlabeled>"
                if desc == "<unlabeled>":
                    results.append(ReplayStep(index=i, kind="click", ok=False,
                                              window_id=live_wid,
                                              notes="click had no accessible name"))
                    continue
                click_result = await click(description=desc, window_id=live_wid)
                ok = getattr(click_result, "ok", True)
                notes_extra = getattr(click_result, "notes", None) or ""
                results.append(ReplayStep(
                    index=i, kind="click", ok=ok, window_id=live_wid,
                    notes=desc + (f" — {notes_extra}" if notes_extra else ""),
                ))
                if not ok:
                    return [r.model_dump() for r in results]

            elif kind == "input":
                field = ev.description or ev.field or "<unlabeled-field>"
                value = getattr(ev, "value", None) or ""
                if value == "<password-redacted>":
                    results.append(ReplayStep(index=i, kind="input", ok=False,
                                              window_id=live_wid,
                                              notes="password field — user must type manually"))
                    return [r.model_dump() for r in results]
                type_result = await type_text(field=field, text=value, window_id=live_wid)
                ok = getattr(type_result, "ok", True)
                notes_extra = getattr(type_result, "notes", None) or ""
                results.append(ReplayStep(
                    index=i, kind="input", ok=ok, window_id=live_wid,
                    notes=f"{field}={value[:40]}" + (f" — {notes_extra}" if notes_extra else ""),
                ))
                if not ok:
                    return [r.model_dump() for r in results]

            elif kind == "key":
                # Replay special keys (Enter/Tab/Escape/Arrow*) via keyboard.press.
                # Most flows just need Enter to submit forms.
                key = ev.description or ""
                if not key:
                    results.append(ReplayStep(index=i, kind="key", ok=False,
                                              window_id=live_wid, notes="empty key"))
                    continue
                try:
                    from .state import get_page  # noqa: PLC0415
                    page = await get_page(live_wid)
                    await page.keyboard.press(key)
                    results.append(ReplayStep(index=i, kind="key", ok=True,
                                              window_id=live_wid, notes=key))
                except Exception as e:
                    results.append(ReplayStep(index=i, kind="key", ok=False,
                                              window_id=live_wid,
                                              notes=f"{key}: {type(e).__name__}"))

            elif kind == "snapshot":
                results.append(ReplayStep(index=i, kind="skipped", ok=True,
                                          window_id=live_wid,
                                          notes="legacy snapshot event — informational only"))

            else:
                results.append(ReplayStep(index=i, kind=kind, ok=False,
                                          window_id=live_wid,
                                          notes=f"unknown event kind: {kind!r}"))

        except Exception as e:
            results.append(ReplayStep(index=i, kind=kind, ok=False,
                                      window_id=rec_wid,
                                      notes=f"error: {type(e).__name__}: {str(e)[:120]}"))
            return [r.model_dump() for r in results]

    return [r.model_dump() for r in results]

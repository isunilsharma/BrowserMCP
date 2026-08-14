"""Phase 4 v0.4 event capture for /record-flow.

Architectural change from v0.3:
  • Events are pushed directly to Python via `page.expose_function("__browsermcp_send")`.
    The buffer-and-drain model is now only a fallback for the brief window
    between recorder install and expose_function binding on a brand-new doc.
  • Direct push means cross-origin navigations DO NOT lose events — there's
    no per-document buffer left behind on the old origin.
  • `context.add_init_script` already applies the recorder to every frame
    (main + iframes), and `page.expose_function` exposes the upload channel
    to every frame of a page. Iframe capture works for free.
  • Shadow DOM: the JS now patches `Element.prototype.attachShadow` and runs
    a `MutationObserver` to attach listeners inside every open shadow root
    as it appears. Closed shadow roots remain inaccessible (browser design).

Remaining edge: the password field's VALUE is intentionally never captured —
the recorder sees the field LABEL only, so replay knows which field to focus,
and the user types the password fresh. This is a security feature, not a bug
(see docs/security.md "no credentials in repo, ever").
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from .state import get_page, get_recording_session, set_recording_session


# ──────────────────────────────────────────────────────────────────────────────
# The injected recorder script
#
# Runs in every document via `context.add_init_script`. Idempotent per-document.
# On each event, calls `window.__browsermcp_send(evt)` to deliver directly to
# Python. If that channel isn't bound yet (extremely narrow window on brand-new
# pages), buffers to sessionStorage so the fallback drain can pick it up.
# ──────────────────────────────────────────────────────────────────────────────

_RECORDER_SCRIPT = """
(() => {
  if (window.__browsermcp_installed) return;
  window.__browsermcp_installed = true;

  const STORAGE_KEY = '__browsermcp_events_v1';
  const readBuffer = () => {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) { return []; }
  };
  const writeBuffer = (arr) => {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(arr)); } catch (e) {}
  };

  window.__browsermcp_events = readBuffer();
  window.__browsermcp_inputTimers = new WeakMap();

  // Primary path: send event straight to Python via the exposed function.
  // Fallback: buffer + sessionStorage for the brief pre-binding window.
  const push = (evt) => {
    try {
      if (typeof window.__browsermcp_send === 'function') {
        // Fire-and-forget — Python returns a Promise we don't await.
        window.__browsermcp_send(evt);
        return;
      }
      window.__browsermcp_events.push(evt);
      writeBuffer(window.__browsermcp_events);
    } catch (e) {}
  };

  // Drain — used by the fallback path only.
  window.__browsermcp_drain = () => {
    const events = window.__browsermcp_events || [];
    window.__browsermcp_events = [];
    try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) {}
    return events;
  };

  // ── Event handlers ─────────────────────────────────────────────────────────

  const captureClick = (e) => {
    try {
      const el = e.target;
      if (!el) return;
      const role = (el.getAttribute && el.getAttribute('role'))
                   || (el.tagName || '').toLowerCase();
      const name = ((el.getAttribute && el.getAttribute('aria-label'))
                  || el.innerText
                  || el.value
                  || (el.getAttribute && el.getAttribute('title'))
                  || '').trim().slice(0, 120);
      push({
        timestamp: new Date().toISOString(),
        kind: 'click',
        description: name || '<unlabeled>',
        role,
        tag: (el.tagName || '').toLowerCase(),
        url: window.location.href,
      });
    } catch (e) {}
  };

  const captureInput = (e) => {
    try {
      const el = e.target;
      if (!el) return;
      const isPassword = el.type === 'password';
      const fieldLabel = ((el.getAttribute && el.getAttribute('aria-label'))
                        || el.placeholder
                        || el.name
                        || '').trim().slice(0, 80);
      push({
        timestamp: new Date().toISOString(),
        kind: 'input',
        description: fieldLabel || '<unlabeled-input>',
        field: fieldLabel,
        value: isPassword ? '<password-redacted>' : (el.value || '').slice(0, 200),
        url: window.location.href,
      });
    } catch (e) {}
  };

  const captureInputDebounced = (e) => {
    try {
      const el = e.target;
      if (!el) return;
      const prev = window.__browsermcp_inputTimers.get(el);
      if (prev) clearTimeout(prev);
      const timer = setTimeout(() => {
        captureInput(e);
        window.__browsermcp_inputTimers.delete(el);
      }, 500);
      window.__browsermcp_inputTimers.set(el, timer);
    } catch (e) {}
  };

  const flushPendingInputs = () => {
    try {
      const el = document.activeElement;
      if (!el) return;
      const timer = window.__browsermcp_inputTimers.get(el);
      if (timer) {
        clearTimeout(timer);
        window.__browsermcp_inputTimers.delete(el);
        captureInput({ target: el });
      }
    } catch (e) {}
  };

  const captureKey = (e) => {
    try {
      const key = e.key;
      if (!['Enter','Tab','Escape','ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(key)) {
        return;
      }
      if (key === 'Enter') flushPendingInputs();
      const el = e.target;
      const fieldLabel = el && ((el.getAttribute && el.getAttribute('aria-label'))
                              || el.placeholder
                              || el.name
                              || el.tagName) || '';
      push({
        timestamp: new Date().toISOString(),
        kind: 'key',
        description: key,
        field: String(fieldLabel).trim().slice(0, 80),
        url: window.location.href,
      });
    } catch (e) {}
  };

  // ── Listener installation ─────────────────────────────────────────────────

  const attachListenersTo = (root) => {
    try {
      root.addEventListener('click', captureClick, { capture: true });
      root.addEventListener('input', captureInputDebounced, { capture: true });
      root.addEventListener('change', captureInput, { capture: true });
      root.addEventListener('keydown', captureKey, { capture: true });
    } catch (e) {}
  };

  attachListenersTo(document);

  // Shadow DOM: walk existing tree + patch attachShadow + MutationObserver.
  const attachToShadowRoot = (root) => {
    try {
      if (!root || root.__browsermcp_attached) return;
      root.__browsermcp_attached = true;
      attachListenersTo(root);
    } catch (e) {}
  };

  const walkForShadow = (node) => {
    try {
      if (!node) return;
      if (node.shadowRoot) {
        attachToShadowRoot(node.shadowRoot);
        walkForShadow(node.shadowRoot);
      }
      const children = node.children || (node.childNodes ? Array.from(node.childNodes).filter(n => n.nodeType === 1) : []);
      for (let i = 0; i < children.length; i++) walkForShadow(children[i]);
    } catch (e) {}
  };

  try {
    const _origAttachShadow = Element.prototype.attachShadow;
    Element.prototype.attachShadow = function(init) {
      const root = _origAttachShadow.apply(this, arguments);
      attachToShadowRoot(root);
      return root;
    };
  } catch (e) {}

  walkForShadow(document.documentElement || document);

  try {
    new MutationObserver((muts) => {
      for (let i = 0; i < muts.length; i++) {
        const added = muts[i].addedNodes;
        for (let j = 0; j < added.length; j++) {
          const n = added[j];
          if (n.nodeType === 1) walkForShadow(n);
        }
      }
    }).observe(document.documentElement || document, { childList: true, subtree: true });
  } catch (e) {}

  // ── SPA route-change capture ─────────────────────────────────────────────

  try {
    const _pushState = history.pushState.bind(history);
    const _replaceState = history.replaceState.bind(history);
    history.pushState = function() {
      const r = _pushState.apply(history, arguments);
      push({
        timestamp: new Date().toISOString(),
        kind: 'navigate',
        url: window.location.href,
        title: document.title,
        nav_source: 'pushState',
      });
      return r;
    };
    history.replaceState = function() {
      const r = _replaceState.apply(history, arguments);
      push({
        timestamp: new Date().toISOString(),
        kind: 'navigate',
        url: window.location.href,
        title: document.title,
        nav_source: 'replaceState',
      });
      return r;
    };
  } catch (e) {}

  window.addEventListener('popstate', () => {
    push({
      timestamp: new Date().toISOString(),
      kind: 'navigate',
      url: window.location.href,
      title: document.title,
      nav_source: 'popstate',
    });
  });

  // Initial-load event for THIS document.
  push({
    timestamp: new Date().toISOString(),
    kind: 'navigate',
    url: window.location.href,
    title: document.title,
    nav_source: 'load',
  });
})();
"""

# Function-form for use with page.evaluate() on already-loaded tabs
# (add_init_script only takes effect on FUTURE documents).
_RECORDER_FN = "() => { " + _RECORDER_SCRIPT.strip() + " }"

_DRAIN_FN = """
() => {
  if (window.__browsermcp_drain) return window.__browsermcp_drain();
  return [];
}
"""


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _coerce(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


async def _bootstrap_current_doc(page) -> bool:
    """Eval the recorder in the page's CURRENT document. add_init_script only
    applies to FUTURE docs, so for already-loaded tabs we need this once."""
    try:
        await page.evaluate(_RECORDER_FN)
        return True
    except Exception:
        return False


async def _drain_page(page) -> list[dict]:
    """Fallback drain — only picks up events buffered before __browsermcp_send
    was bound on this document. Usually empty."""
    try:
        raw = await page.evaluate(_DRAIN_FN)
        events = _coerce(raw)
        return events if isinstance(events, list) else []
    except Exception:
        return []


async def _expose_send_function(page, window_id: str, session: dict) -> bool:
    """Bind the per-page __browsermcp_send so JS pushes events straight to Python.
    The handler closes over (window_id, session) to tag events correctly."""
    async def _handler(event: dict) -> None:
        try:
            if not isinstance(event, dict):
                return
            event["window_id"] = window_id
            session["accumulated_events"].append(event)
        except Exception:
            pass

    try:
        await page.expose_function("__browsermcp_send", _handler)
        return True
    except Exception:
        # Already exposed (e.g. on reattach) — that's fine.
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Fallback background drain — picks up anything the realtime channel missed
# ──────────────────────────────────────────────────────────────────────────────

_DRAIN_INTERVAL_S = 2.0


async def _auto_drain_loop():
    while True:
        try:
            await asyncio.sleep(_DRAIN_INTERVAL_S)
            session = await get_recording_session()
            if session is None:
                return
            entries = list(session["tracked_pages"])
            for entry in entries:
                page = entry["page"]
                wid = entry["window_id"]
                if page.is_closed():
                    continue
                events = await _drain_page(page)
                for e in events:
                    if isinstance(e, dict):
                        e["window_id"] = wid
                if events:
                    session["accumulated_events"].extend(events)
        except asyncio.CancelledError:
            return
        except Exception:
            continue


# ──────────────────────────────────────────────────────────────────────────────
# Session API
# ──────────────────────────────────────────────────────────────────────────────

async def start_recording_session() -> dict[str, Any]:
    from .state import _state, _lock  # noqa: PLC0415

    async with _lock:
        context = _state.get("context")
        if context is None:
            raise RuntimeError("Browser not attached; call chrome_attach first")

        session_id = str(uuid.uuid4())[:8]
        tracked_pages: list = []
        accumulated_events: list[dict] = []

        session = {
            "session_id": session_id,
            "tracked_pages": tracked_pages,
            "accumulated_events": accumulated_events,
            "context": context,
        }
        # Stash early so the _on_new_page closure can reach it.
        _state["recording_session"] = session

        # 1. Install recorder context-wide so every future document gets it.
        try:
            await context.add_init_script(_RECORDER_SCRIPT)
            init_script_ok = True
        except Exception:
            init_script_ok = False

        # 2. Bootstrap + expose channel on every currently-open tab.
        existing = [p for p in context.pages if not p.is_closed()]
        for page in existing:
            wid = f"w-existing-{uuid.uuid4().hex[:6]}"
            tracked_pages.append({"page": page, "window_id": wid, "anchor": False})
            await _expose_send_function(page, wid, session)
            await _bootstrap_current_doc(page)

        # 3. Open the fresh anchor tab.
        anchor_page = await context.new_page()
        anchor_wid = f"w-anchor-{session_id}"
        tracked_pages.append({"page": anchor_page, "window_id": anchor_wid, "anchor": True})
        await _expose_send_function(anchor_page, anchor_wid, session)
        await _bootstrap_current_doc(anchor_page)
        _state["windows"][anchor_wid] = anchor_page

        # 4. Auto-handle new tabs as they open.
        def _on_new_page(new_page):
            wid = f"w-new-{uuid.uuid4().hex[:6]}"
            tracked_pages.append({"page": new_page, "window_id": wid, "anchor": False})

            async def _setup():
                await _expose_send_function(new_page, wid, session)
                await _bootstrap_current_doc(new_page)
            asyncio.ensure_future(_setup())

        context.on("page", _on_new_page)

        # 5. Start the fallback background drain.
        drain_task = asyncio.ensure_future(_auto_drain_loop())

        session["anchor_window_id"] = anchor_wid
        session["anchor_page"] = anchor_page
        session["_on_new_page"] = _on_new_page
        session["_drain_task"] = drain_task
        session["init_script_ok"] = init_script_ok

    return {
        "session_id": session_id,
        "anchor_window_id": anchor_wid,
        "existing_tabs": len(existing),
        "init_script_ok": init_script_ok,
        "realtime_channel": "expose_function",
        "fallback_drain_interval_s": _DRAIN_INTERVAL_S,
    }


async def drain_session_events() -> list[dict]:
    """Manual fallback drain. Usually returns [] because the realtime channel
    has already delivered everything."""
    session = await get_recording_session()
    if session is None:
        raise RuntimeError("No active recording session")

    fresh_events: list[dict] = []
    entries = list(session["tracked_pages"])
    for entry in entries:
        page = entry["page"]
        wid = entry["window_id"]
        if page.is_closed():
            continue
        events = await _drain_page(page)
        for e in events:
            if isinstance(e, dict):
                e["window_id"] = wid
        fresh_events.extend(events)

    session["accumulated_events"].extend(fresh_events)
    return fresh_events


async def stop_recording_session() -> list[dict]:
    session = await get_recording_session()
    if session is None:
        raise RuntimeError("No active recording session")

    drain_task = session.get("_drain_task")
    if drain_task is not None and not drain_task.done():
        drain_task.cancel()
        try:
            await drain_task
        except (asyncio.CancelledError, Exception):
            pass

    # Final fallback sweep.
    await drain_session_events()

    context = session.get("context")
    listener = session.get("_on_new_page")
    if context is not None and listener is not None:
        try:
            context.remove_listener("page", listener)
        except Exception:
            pass

    all_events = session["accumulated_events"]
    await set_recording_session(None)
    return all_events


# ──────────────────────────────────────────────────────────────────────────────
# Backwards-compat single-tab API
# ──────────────────────────────────────────────────────────────────────────────

async def install_recorder(window_id: str) -> dict[str, Any]:
    page = await get_page(window_id)
    ok = await _bootstrap_current_doc(page)
    return {"installed": ok, "already_installed": False}


async def drain_events(window_id: str) -> list[dict]:
    page = await get_page(window_id)
    return await _drain_page(page)

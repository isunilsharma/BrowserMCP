"""File-attachment primitive for HTML ``<input type="file">`` fields.

This is the one primitive that moves data *off* the machine: whatever local file
we hand to a file input gets uploaded to whatever site the page belongs to. That
makes it the highest-stakes write tool in the set, so it is gated harder than
``click``/``type_text``:

* ``confirmed=True`` is always required — there is no read-only mode.
* The path must resolve to a real, regular file the user owns.
* Paths that live in known credential stores are refused outright, as are file
  extensions that are almost always secrets rather than documents.
* Uploads are size-capped so a mis-typed path can't stream a disk image.

See ``docs/security.md`` §3 (data egress) before loosening any of this.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..models import AttachFileResult
from ..state import get_page

try:
    from playwright.async_api import TimeoutError as _PlaywrightTimeoutError
except ImportError:  # pragma: no cover - playwright is in [project.dependencies]
    _PlaywrightTimeoutError = asyncio.TimeoutError

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Directories that hold credentials rather than documents. Matched against the
# resolved path's parts so "~/.ssh/id_rsa" is caught however it was written.
_DENIED_DIR_PARTS = frozenset(
    {
        ".ssh",
        ".aws",
        ".gnupg",
        ".kube",
        ".docker",
        ".config/gcloud",
        ".browsermcp",
        "keychains",
        "login.keychain-db",
    }
)

_DENIED_SUFFIXES = frozenset(
    {".pem", ".key", ".p12", ".pfx", ".keychain", ".kdbx", ".jks", ".ppk"}
)

_DENIED_NAMES = frozenset({".env", "credentials", "id_rsa", "id_ed25519", ".netrc"})


def _vet_path(raw: str) -> Path:
    """Resolve raw and raise ValueError if it isn't safe to upload."""
    path = Path(raw).expanduser().resolve()

    if not path.exists():
        raise ValueError(f"no such file: {path}")
    if not path.is_file():
        raise ValueError(f"not a regular file: {path}")

    lowered_parts = {part.lower() for part in path.parts}
    if lowered_parts & _DENIED_DIR_PARTS:
        raise ValueError(
            f"refusing to upload {path.name}: path crosses a credential directory. "
            "See docs/security.md §3."
        )
    if path.suffix.lower() in _DENIED_SUFFIXES:
        raise ValueError(
            f"refusing to upload {path.name}: {path.suffix} files are treated as secrets"
        )
    if path.name.lower() in _DENIED_NAMES:
        raise ValueError(f"refusing to upload {path.name}: treated as a credential file")

    size = path.stat().st_size
    if size == 0:
        raise ValueError(f"refusing to upload {path.name}: file is empty")
    if size > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"refusing to upload {path.name}: {size} bytes exceeds the "
            f"{MAX_UPLOAD_BYTES}-byte cap"
        )

    return path


async def attach_file(
    field: str,
    paths: str | list[str],
    window_id: str | None = None,
    confirmed: bool = False,
    timeout_s: float = 15.0,
    frame: str | None = None,
) -> AttachFileResult:
    """Attach one or more local files to the file input matching field.

    ``field`` may be a CSS selector (anything containing ``#``, ``.``, or ``[``),
    an element id, or the visible label text of the upload control. When the page
    has exactly one ``<input type="file">`` the field is used only for reporting
    and the lone input is selected.

    Uploading sends file contents to the remote origin, so ``confirmed=True`` is
    mandatory — there is no dry-run form of this call.

    Raises ValueError for unsafe or missing paths, and stdlib TimeoutError if the
    input can't be resolved within timeout_s.
    """
    if not confirmed:
        return AttachFileResult(
            field=field,
            ok=False,
            notes=(
                "confirmation_required: attaching a file uploads its contents to the "
                "page's origin; caller must re-invoke with confirmed=True"
            ),
        )

    raw_paths = [paths] if isinstance(paths, str) else list(paths)
    if not raw_paths:
        raise ValueError("attach_file requires at least one path")

    vetted = [_vet_path(p) for p in raw_paths]
    total_bytes = sum(p.stat().st_size for p in vetted)

    page = await get_page(window_id)
    root = page.frame_locator(frame) if frame else page
    timeout_ms = int(timeout_s * 1000)

    locator, note = await _resolve_file_input(root, field, timeout_ms)

    try:
        await asyncio.wait_for(
            locator.set_input_files([str(p) for p in vetted], timeout=timeout_ms),
            timeout=timeout_s + 2.0,
        )
    except (TimeoutError, _PlaywrightTimeoutError) as exc:
        raise TimeoutError(
            f"attach_file to {field!r} did not complete within {timeout_s}s"
        ) from exc

    return AttachFileResult(
        field=field,
        files=[p.name for p in vetted],
        total_bytes=total_bytes,
        ok=True,
        notes=note,
    )


async def _resolve_file_input(root, field: str, timeout_ms: int):
    """Return (locator, note) for the file input identified by field."""
    all_inputs = root.locator('input[type="file"]')
    try:
        count = await all_inputs.count()
    except Exception:
        count = 0

    if count == 1:
        return all_inputs.first, "matched the page's only file input"

    if any(ch in field for ch in "#.[") or field.startswith("input"):
        return root.locator(field), f"matched CSS selector {field!r}"

    by_id = root.locator(f'input[type="file"]#{field}')
    try:
        if await by_id.count() > 0:
            return by_id.first, f"matched file input with id {field!r}"
    except Exception:
        pass

    # Fall back to the file input nearest a container mentioning the label text.
    labelled = root.locator(
        f'div:has-text("{field}") input[type="file"], '
        f'label:has-text("{field}") input[type="file"]'
    )
    try:
        if await labelled.count() > 0:
            return labelled.first, f"matched file input labelled {field!r}"
    except Exception:
        pass

    if count > 1:
        raise ValueError(
            f"{count} file inputs on the page and none matched {field!r} — "
            "pass a CSS selector or element id instead"
        )
    raise ValueError(f"no file input matched {field!r}")

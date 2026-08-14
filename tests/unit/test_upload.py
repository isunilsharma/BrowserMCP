import asyncio

import pytest

from browsermcp.tools.upload import (
    MAX_UPLOAD_BYTES,
    _vet_path,
    attach_file,
)


def _write(tmp_path, name: str, size: int = 16):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x" * size)
    return p


def test_vet_path_accepts_ordinary_file(tmp_path):
    p = _write(tmp_path, "resume.pdf")
    assert _vet_path(str(p)) == p.resolve()


def test_vet_path_expands_user(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    _write(tmp_path, "cv.pdf")
    assert _vet_path("~/cv.pdf").name == "cv.pdf"


def test_vet_path_rejects_missing_file(tmp_path):
    with pytest.raises(ValueError, match="no such file"):
        _vet_path(str(tmp_path / "nope.pdf"))


def test_vet_path_rejects_directory(tmp_path):
    with pytest.raises(ValueError, match="not a regular file"):
        _vet_path(str(tmp_path))


def test_vet_path_rejects_empty_file(tmp_path):
    p = _write(tmp_path, "empty.pdf", size=0)
    with pytest.raises(ValueError, match="file is empty"):
        _vet_path(str(p))


def test_vet_path_rejects_oversize_file(tmp_path):
    p = _write(tmp_path, "huge.pdf", size=MAX_UPLOAD_BYTES + 1)
    with pytest.raises(ValueError, match="exceeds the"):
        _vet_path(str(p))


@pytest.mark.parametrize("rel", [".ssh/id_rsa_backup.pdf", ".aws/notes.pdf", ".gnupg/x.pdf"])
def test_vet_path_rejects_credential_directories(tmp_path, rel):
    p = _write(tmp_path, rel)
    with pytest.raises(ValueError, match="credential directory"):
        _vet_path(str(p))


@pytest.mark.parametrize("name", ["server.pem", "private.key", "bundle.p12", "store.jks"])
def test_vet_path_rejects_secret_suffixes(tmp_path, name):
    p = _write(tmp_path, name)
    with pytest.raises(ValueError, match="treated as secrets"):
        _vet_path(str(p))


@pytest.mark.parametrize("name", [".env", "credentials", "id_rsa", ".netrc"])
def test_vet_path_rejects_credential_filenames(tmp_path, name):
    p = _write(tmp_path, name)
    with pytest.raises(ValueError, match="credential file"):
        _vet_path(str(p))


def test_attach_file_requires_confirmation(tmp_path):
    p = _write(tmp_path, "resume.pdf")
    result = asyncio.run(attach_file("resume", str(p)))
    assert result.ok is False
    assert "confirmation_required" in result.notes
    assert result.files == []


def test_attach_file_confirmation_gate_precedes_path_check():
    """An unconfirmed call must not leak whether a path exists."""
    result = asyncio.run(attach_file("resume", "/nonexistent/secret.pdf"))
    assert result.ok is False
    assert "confirmation_required" in result.notes


def test_attach_file_rejects_empty_path_list():
    with pytest.raises(ValueError, match="at least one path"):
        asyncio.run(attach_file("resume", [], confirmed=True))

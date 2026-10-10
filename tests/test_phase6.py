from uuid import uuid4
from pathlib import Path

import pytest

from jayai.browser import allowed_url
from jayai.files import UserWorkspace


def test_file_operations_support_python_without_is_junction(tmp_path, monkeypatch):
    monkeypatch.delattr(Path, "is_junction", raising=False)
    workspace = UserWorkspace(tmp_path)
    user = uuid4()
    assert workspace.write(user, "note.txt", "private")["bytes"] == 7
    assert workspace.read(user, "note.txt") == {"text": "private"}
    assert workspace.list(user) == {"names": ["note.txt"]}


def test_files_are_isolated_by_user(tmp_path):
    workspace = UserWorkspace(tmp_path)
    one, two = uuid4(), uuid4()
    assert workspace.write(one, "note.txt", "private") == {"path": "note.txt", "bytes": 7}
    assert workspace.read(one, "note.txt") == {"text": "private"}
    assert workspace.list(one) == {"names": ["note.txt"]}
    with pytest.raises(ValueError):
        workspace.read(two, "note.txt")


def test_files_block_traversal_absolute_paths_and_links(tmp_path):
    workspace = UserWorkspace(tmp_path / "users")
    user = uuid4()
    for name in ("../escape.txt", "C:\\outside\\test.txt", "/tmp/escape.txt"):
        with pytest.raises(ValueError):
            workspace.write(user, name, "no")
    outside = tmp_path / "outside.txt"
    outside.write_text("private")
    link = workspace.path(user, "link.txt")
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Creating symlinks requires privilege on this system")
    with pytest.raises(PermissionError):
        workspace.read(user, "link.txt")


def test_browser_url_must_be_exact_allowed_https_host():
    hosts = frozenset({"example.com"})
    assert allowed_url("https://example.com/articles", hosts)
    for url in ("http://example.com", "https://example.com.evil.test",
                "https://user:secret@example.com", "https://example.com:8443",
                "https://127.0.0.1", "file:///etc/passwd", "https://example.com@evil.test"):
        assert not allowed_url(url, hosts)


def test_browser_rejects_private_literal_even_if_allowed():
    assert not allowed_url("https://127.0.0.1", frozenset({"127.0.0.1"}))
    assert not allowed_url("https://localhost", frozenset({"localhost"}))


def test_linked_user_root_is_rejected_for_read_write_and_list(tmp_path):
    from uuid import UUID

    workspace = UserWorkspace(tmp_path / "users")
    user_a = UUID("00000000-0000-0000-0000-000000000001")
    user_b = UUID("00000000-0000-0000-0000-000000000002")

    workspace.write(user_b, "private.txt", "B-owned")

    root_a = workspace.base / str(user_a)
    root_b = workspace.base / str(user_b)
    root_a.mkdir()
    root_a.rmdir()

    try:
        root_a.symlink_to(root_b, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Directory symlinks unavailable: {exc}")

    with pytest.raises(PermissionError):
        workspace.read(user_a, "private.txt")

    with pytest.raises(PermissionError):
        workspace.write(user_a, "private.txt", "must-not-change")

    with pytest.raises(PermissionError):
        workspace.list(user_a)

    assert workspace.read(user_b, "private.txt") == {"text": "B-owned"}

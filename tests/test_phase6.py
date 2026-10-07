from uuid import uuid4

import pytest

from jayai.browser import allowed_url
from jayai.files import UserWorkspace


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
    for name in ("../escape.txt", "C:\\Windows\\test.txt", "/tmp/escape.txt"):
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

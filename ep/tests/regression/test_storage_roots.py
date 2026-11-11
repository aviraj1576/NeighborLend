import pytest

from ep_engine.storage.local import LocalStorage
from ep_engine.storage.repository import Repository


def test_storage_refuses_a_symlinked_root_before_writing(tmp_path, monkeypatch):
    root = tmp_path / "redirected-evidence"
    path_type = type(root)
    original = path_type.is_symlink
    monkeypatch.setattr(path_type, "is_symlink", lambda value: value == root or original(value))
    with pytest.raises(ValueError, match="private storage"):
        LocalStorage(root)
    assert not root.exists()


def test_database_refuses_symlink_before_connecting(tmp_path, monkeypatch):
    path = tmp_path / "redirected.sqlite3"
    path_type = type(path)
    original = path_type.is_symlink
    monkeypatch.setattr(path_type, "is_symlink", lambda value: value == path or original(value))
    with pytest.raises(ValueError, match="database"):
        Repository(path)
    assert not path.exists()

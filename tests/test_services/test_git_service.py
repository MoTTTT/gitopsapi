"""
Unit tests for GitService — mocks gitpython so no real repo is needed.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from gitopsgui.services.git_service import GitService


@pytest.fixture()
def svc(tmp_path):
    s = GitService()
    s._git_repo = MagicMock()   # inject a mock repo (instance-based)
    s._local_path = tmp_path    # point at tmp dir for file operations
    return s


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

async def test_read_file_returns_contents(svc, tmp_path):
    f = tmp_path / "test.yaml"
    f.write_text("key: value\n")
    result = await svc.read_file("test.yaml")
    assert result == "key: value\n"


async def test_read_file_missing_raises(svc):
    with pytest.raises(FileNotFoundError):
        await svc.read_file("missing.yaml")


# ---------------------------------------------------------------------------
# list_dir
# ---------------------------------------------------------------------------

async def test_list_dir_returns_subdirs(svc, tmp_path):
    (tmp_path / "dir-a").mkdir()
    (tmp_path / "dir-b").mkdir()
    (tmp_path / "file.yaml").write_text("")
    result = await svc.list_dir(".")
    assert set(result) == {"dir-a", "dir-b"}


async def test_list_dir_nonexistent_returns_empty(svc):
    result = await svc.list_dir("nonexistent")
    assert result == []


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------

async def test_write_file_creates_file_and_stages(svc, tmp_path):
    await svc.write_file("subdir/test.yaml", "content: 42\n")
    assert (tmp_path / "subdir" / "test.yaml").read_text() == "content: 42\n"
    svc._get_repo().index.add.assert_called_once()


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------

async def test_commit_returns_sha(svc):
    mock_commit = MagicMock()
    mock_commit.hexsha = "abc123def456"
    svc._get_repo().index.commit.return_value = mock_commit

    result = await svc.commit("test commit")
    assert result == "abc123def456"


# ---------------------------------------------------------------------------
# _get_repo raises if not initialised (no repo_url, no _git_repo)
# ---------------------------------------------------------------------------

def test_get_repo_raises_if_not_initialised():
    svc = GitService(repo_url="")  # explicit empty → _repo_url is ""
    # _git_repo is None and _repo_url is "" → should raise RuntimeError
    with pytest.raises(RuntimeError, match="not initialised"):
        svc._get_repo()

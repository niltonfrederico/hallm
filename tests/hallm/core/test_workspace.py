"""Tests for hallm.core.workspace repo discovery."""

from pathlib import Path

import pytest
import typer

from hallm.core import workspace


def _make_hallm_checkout(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text('[project]\nname = "hallm"\n')
    return root


def _make_other_checkout(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text('[project]\nname = "something-else"\n')
    return root


class TestFindRepoFromEnv:
    def test_env_var_wins(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo = _make_hallm_checkout(tmp_path / "repo")
        monkeypatch.setenv("HALLM_REPO", str(repo))
        monkeypatch.chdir(tmp_path)  # cwd has no marker
        assert workspace.find_repo() == repo

    def test_env_var_pointing_at_non_hallm_dir_is_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        wrong = _make_other_checkout(tmp_path / "wrong")
        repo = _make_hallm_checkout(tmp_path / "repo")
        monkeypatch.setenv("HALLM_REPO", str(wrong))
        monkeypatch.chdir(repo)
        # Walk-up should pick up the real one.
        assert workspace.find_repo() == repo

    def test_env_var_pointing_at_missing_path_falls_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HALLM_REPO", str(tmp_path / "does-not-exist"))
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(workspace, "_REPO_POINTER", tmp_path / ".no-pointer")
        assert workspace.find_repo() is None


class TestFindRepoFromWalkUp:
    def test_walks_up_to_find_marker(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo = _make_hallm_checkout(tmp_path / "repo")
        deep = repo / "a" / "b" / "c"
        deep.mkdir(parents=True)
        monkeypatch.delenv("HALLM_REPO", raising=False)
        monkeypatch.chdir(deep)
        monkeypatch.setattr(workspace, "_REPO_POINTER", tmp_path / ".no-pointer")
        assert workspace.find_repo() == repo

    def test_returns_none_when_cwd_has_no_marker(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HALLM_REPO", raising=False)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(workspace, "_REPO_POINTER", tmp_path / ".no-pointer")
        assert workspace.find_repo() is None

    def test_non_hallm_pyproject_does_not_match(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        other = _make_other_checkout(tmp_path / "other")
        monkeypatch.delenv("HALLM_REPO", raising=False)
        monkeypatch.chdir(other)
        monkeypatch.setattr(workspace, "_REPO_POINTER", tmp_path / ".no-pointer")
        assert workspace.find_repo() is None


class TestFindRepoFromPointer:
    def test_pointer_used_when_env_and_walk_up_miss(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _make_hallm_checkout(tmp_path / "repo")
        pointer = tmp_path / "pointer"
        pointer.write_text(f"{repo}\n")
        monkeypatch.delenv("HALLM_REPO", raising=False)
        monkeypatch.chdir(tmp_path)  # no marker in cwd or ancestors
        monkeypatch.setattr(workspace, "_REPO_POINTER", pointer)
        assert workspace.find_repo() == repo

    def test_pointer_pointing_at_non_hallm_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bogus = _make_other_checkout(tmp_path / "bogus")
        pointer = tmp_path / "pointer"
        pointer.write_text(f"{bogus}\n")
        monkeypatch.delenv("HALLM_REPO", raising=False)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(workspace, "_REPO_POINTER", pointer)
        assert workspace.find_repo() is None

    def test_missing_pointer_file_is_silently_ignored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HALLM_REPO", raising=False)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(workspace, "_REPO_POINTER", tmp_path / "absent")
        assert workspace.find_repo() is None


class TestRequireRepo:
    def test_returns_repo_when_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo = _make_hallm_checkout(tmp_path / "repo")
        monkeypatch.setenv("HALLM_REPO", str(repo))
        assert workspace.require_repo() == repo

    def test_exits_with_helpful_message_when_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("HALLM_REPO", raising=False)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(workspace, "_REPO_POINTER", tmp_path / ".no-pointer")
        with pytest.raises(typer.Exit) as excinfo:
            workspace.require_repo()
        assert excinfo.value.exit_code == 1
        stderr = capsys.readouterr().err
        assert "HALLM_REPO" in stderr


class TestIsHallmCheckout:
    def test_malformed_pyproject_is_not_a_checkout(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("not valid = [[[")
        assert workspace._is_hallm_checkout(tmp_path) is False

    def test_missing_pyproject_is_not_a_checkout(self, tmp_path: Path) -> None:
        assert workspace._is_hallm_checkout(tmp_path) is False


def test_find_repo_reflects_env_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-resolves every call so changing $HALLM_REPO mid-run takes effect."""
    repo_a = _make_hallm_checkout(tmp_path / "a")
    repo_b = _make_hallm_checkout(tmp_path / "b")
    monkeypatch.setenv("HALLM_REPO", str(repo_a))
    assert workspace.find_repo() == repo_a
    monkeypatch.setenv("HALLM_REPO", str(repo_b))
    assert workspace.find_repo() == repo_b

"""Unit tests for hallm.cli.base.shell."""

import subprocess
from unittest.mock import patch

import pytest
import typer

from hallm.cli.base.shell import check
from hallm.cli.base.shell import fail
from hallm.cli.base.shell import run
from hallm.cli.base.shell import run_or_fail


def _cp(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRun:
    def test_returns_completed_process(self) -> None:
        cp = _cp(stdout="hello")
        with patch("subprocess.run", return_value=cp):
            result = run(["echo", "hello"])
        assert result is cp

    def test_calls_subprocess_with_text_and_capture(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            run(["ls", "-la"])
        mock.assert_called_once_with(["ls", "-la"], text=True, capture_output=True, env=None)

    def test_echoes_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("subprocess.run", return_value=_cp()):
            run(["kubectl", "get", "pods"])
        assert "+ kubectl get pods" in capsys.readouterr().out

    def test_echoes_multi_word_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("subprocess.run", return_value=_cp()):
            run(["k3d", "cluster", "create", "hallm"])
        assert "+ k3d cluster create hallm" in capsys.readouterr().out

    def test_single_element_command(self) -> None:
        with patch("subprocess.run", return_value=_cp()) as mock:
            run(["ls"])
        mock.assert_called_once_with(["ls"], text=True, capture_output=True, env=None)


# ---------------------------------------------------------------------------
# fail
# ---------------------------------------------------------------------------


class TestFail:
    def test_raises_typer_exit(self) -> None:
        with pytest.raises(typer.Exit):
            fail("something went wrong")

    def test_exit_code_is_1(self) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            fail("boom")
        assert exc_info.value.exit_code == 1

    def test_writes_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit):
            fail("critical error")
        assert "ERROR: critical error" in capsys.readouterr().err

    def test_error_prefix_on_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit):
            fail("details here")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "ERROR:" in captured.err


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


class TestCheck:
    def test_returns_true_when_ok(self) -> None:
        assert check("cluster running", True) is True

    def test_returns_false_when_not_ok(self) -> None:
        assert check("cluster running", False) is False

    def test_ok_status_in_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        check("GPU visible", True)
        assert "[OK]" in capsys.readouterr().out

    def test_fail_status_in_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        check("GPU visible", False)
        assert "[FAIL]" in capsys.readouterr().out

    def test_label_in_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        check("port 443 reachable", True)
        assert "port 443 reachable" in capsys.readouterr().out

    def test_ok_does_not_print_fail(self, capsys: pytest.CaptureFixture[str]) -> None:
        check("some check", True)
        assert "[FAIL]" not in capsys.readouterr().out

    def test_fail_does_not_print_ok(self, capsys: pytest.CaptureFixture[str]) -> None:
        check("some check", False)
        assert "[OK]" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# run_or_fail
# ---------------------------------------------------------------------------


class TestRunOrFail:
    def test_success_returns_process(self) -> None:
        cp = _cp(returncode=0, stdout="ok")
        with patch("subprocess.run", return_value=cp):
            result = run_or_fail(["echo", "ok"], "should not fail")
        assert result is cp

    def test_failure_raises_exit(self) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="boom")):
            with pytest.raises(typer.Exit) as exc_info:
                run_or_fail(["false"], "command failed")
        assert exc_info.value.exit_code == 1

    def test_failure_embeds_stderr_in_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("subprocess.run", return_value=_cp(returncode=1, stderr="detail here")):
            with pytest.raises(typer.Exit):
                run_or_fail(["false"], "the error message")
        err = capsys.readouterr().err
        assert "the error message" in err
        assert "detail here" in err

"""Unit tests for hallm.cli.subcommands.headlamp."""

from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from hallm.cli.subcommands import headlamp
from hallm.cli.subcommands.headlamp import app
from hallm.core.settings import settings
from tests.mocks import completed_process as _cp


@pytest.fixture
def plugin_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Lay out a fake plugin source so _build_plugin/_pack_configmap have something to read."""
    root = tmp_path / "plugins" / "hallm-links"
    (root / "dist").mkdir(parents=True)
    (root / "dist" / "main.js").write_text("// stub bundle\n")
    (root / "package.json").write_text('{"name": "hallm-links"}\n')
    monkeypatch.setattr(settings, "repo_root", tmp_path)
    return root


class TestPluginRoot:
    def test_path_derived_from_settings(self, plugin_root: Path) -> None:
        assert headlamp._plugin_root() == plugin_root


class TestBuildPlugin:
    def test_builds_in_pinned_node_container(self, plugin_root: Path) -> None:
        calls: list[list[str]] = []

        def _capture(cmd: list[str], **_kw: object) -> object:
            calls.append(cmd)
            return _cp()

        with patch("subprocess.run", side_effect=_capture):
            headlamp._build_plugin()

        assert len(calls) == 1
        cmd = calls[0]
        assert cmd[:3] == ["docker", "run", "--rm"]
        assert headlamp._BUILD_IMAGE in cmd
        assert f"{plugin_root}:/work" in cmd
        assert cmd[-1] == "npm install && npm run build"

    def test_missing_plugin_root_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "repo_root", tmp_path)
        with pytest.raises(typer.Exit):
            headlamp._build_plugin()


class TestPackConfigmap:
    def test_replaces_configmap_with_dist_files(self, plugin_root: Path) -> None:
        calls: list[list[str]] = []

        def _capture(cmd: list[str], **_kw: object) -> object:
            calls.append(cmd)
            return _cp()

        with patch("subprocess.run", side_effect=_capture):
            headlamp._pack_configmap()

        assert [
            "kubectl",
            "-n",
            "kube-system",
            "delete",
            "configmap",
            "headlamp-plugin-hallm-links",
        ] in calls
        create = next(c for c in calls if "create" in c and "configmap" in c)
        joined = " ".join(create)
        assert f"--from-file=main.js={plugin_root / 'dist' / 'main.js'}" in joined
        assert f"--from-file=package.json={plugin_root / 'package.json'}" in joined

    def test_missing_build_output_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # plugin source exists but dist/main.js does not — should bail.
        root = tmp_path / "plugins" / "hallm-links"
        root.mkdir(parents=True)
        (root / "package.json").write_text("{}")
        monkeypatch.setattr(settings, "repo_root", tmp_path)
        with pytest.raises(typer.Exit):
            headlamp._pack_configmap()


class TestRestartHeadlamp:
    def test_rollouts_and_waits(self, plugin_root: Path) -> None:
        calls: list[list[str]] = []

        def _capture(cmd: list[str], **_kw: object) -> object:
            calls.append(cmd)
            return _cp()

        with (
            patch("subprocess.run", side_effect=_capture),
            patch("hallm.cli.subcommands.headlamp.kubectl.wait") as wait,
        ):
            headlamp._restart_headlamp()

        assert calls[0] == [
            "kubectl",
            "-n",
            "kube-system",
            "rollout",
            "restart",
            "deployment/headlamp",
        ]
        wait.assert_called_once()


class TestSyncCommand:
    def test_full_flow(self, runner: CliRunner, plugin_root: Path) -> None:
        # Typer collapses a single-command app: invoking without a subcommand
        # name dispatches directly to that command.
        with (
            patch("hallm.cli.subcommands.headlamp._build_plugin") as build,
            patch("hallm.cli.subcommands.headlamp._pack_configmap") as pack,
            patch("hallm.cli.subcommands.headlamp._restart_headlamp") as restart,
        ):
            result = runner.invoke(app, [])

        assert result.exit_code == 0
        build.assert_called_once()
        pack.assert_called_once()
        restart.assert_called_once()
        assert "Visit https://headlamp.hallm.local" in result.output

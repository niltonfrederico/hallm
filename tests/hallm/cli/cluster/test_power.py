"""Tests for hallm.cli.subcommands.cluster.power (start / stop)."""

from unittest.mock import patch

from hallm.cli.subcommands.cluster import app


class TestStop:
    def test_calls_scale_with_zero(self, runner) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.power.kubectl.scale_by_label",
            return_value=["immich-server", "immich-machine-learning"],
        ) as mock:
            result = runner.invoke(app, ["stop", "immich"])
        assert result.exit_code == 0
        mock.assert_called_once_with("app=immich", 0, namespace="default")

    def test_echoes_count_and_names(self, runner) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.power.kubectl.scale_by_label",
            return_value=["immich-server", "immich-machine-learning"],
        ):
            result = runner.invoke(app, ["stop", "immich"])
        assert "Stopped 2 deployment(s)" in result.output
        assert "immich-server" in result.output

    def test_custom_namespace_passed_through(self, runner) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.power.kubectl.scale_by_label",
            return_value=["x"],
        ) as mock:
            result = runner.invoke(app, ["stop", "x", "-n", "kube-system"])
        assert result.exit_code == 0
        mock.assert_called_once_with("app=x", 0, namespace="kube-system")


class TestStart:
    def test_calls_scale_with_one(self, runner) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.power.kubectl.scale_by_label",
            return_value=["immich-server"],
        ) as mock:
            result = runner.invoke(app, ["start", "immich"])
        assert result.exit_code == 0
        mock.assert_called_once_with("app=immich", 1, namespace="default")

    def test_echoes_count_and_names(self, runner) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.power.kubectl.scale_by_label",
            return_value=["paperless", "paperless-tika"],
        ):
            result = runner.invoke(app, ["start", "paperless"])
        assert "Started 2 deployment(s)" in result.output
        assert "paperless-tika" in result.output

    def test_custom_namespace_passed_through(self, runner) -> None:
        with patch(
            "hallm.cli.subcommands.cluster.power.kubectl.scale_by_label",
            return_value=["y"],
        ) as mock:
            result = runner.invoke(app, ["start", "y", "--namespace", "foo"])
        assert result.exit_code == 0
        mock.assert_called_once_with("app=y", 1, namespace="foo")

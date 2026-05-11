"""Tests for setup_builders.base: WaitCondition, App, Step, build_setup_pipeline."""

from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

import pytest

from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import SetupStepError
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.cli.subcommands.cluster.setup_builders.base import WaitCondition
from hallm.cli.subcommands.cluster.setup_builders.base import build_setup_pipeline
from tests.mocks import completed_process as _cp

# ---------------------------------------------------------------------------
# Enum + exception
# ---------------------------------------------------------------------------


class TestWaitCondition:
    def test_values(self) -> None:
        assert WaitCondition.AVAILABLE.value == "Available"
        assert WaitCondition.READY.value == "Ready"
        assert WaitCondition.COMPLETE.value == "complete"


class TestSetupStepError:
    def test_carries_step_name(self) -> None:
        err = SetupStepError("bang", step_name="alpha")
        assert err.step_name == "alpha"
        assert "bang" in str(err)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


class _StubApp(App):
    name: ClassVar[str] = "stub"
    manifest_path: ClassVar[Path | None] = Path("/tmp/never-read")


class TestAppInstall:
    def test_path_branch(self, tmp_path: Path) -> None:
        manifest = tmp_path / "stub.yaml"
        manifest.write_text("kind: ConfigMap\n")

        class _App(App):
            name: ClassVar[str] = "stub"
            manifest_path: ClassVar[Path | None] = manifest

        with patch("hallm.cli.subcommands.cluster.setup_builders.base.kubectl.apply") as mock_apply:
            _App().install()
        mock_apply.assert_called_once()
        assert mock_apply.call_args.args[0] == "kind: ConfigMap\n"

    def test_url_branch(self) -> None:
        class _App(App):
            name: ClassVar[str] = "stub"
            manifest_url: ClassVar[str | None] = "https://example.test/m.yaml"

        with patch(
            "hallm.cli.subcommands.cluster.setup_builders.base.kubectl.apply_url"
        ) as mock_apply:
            _App().install()
        mock_apply.assert_called_once_with("https://example.test/m.yaml")

    def test_no_source_raises(self) -> None:
        class _App(App):
            name: ClassVar[str] = "stub"

        with pytest.raises(NotImplementedError):
            _App().install()


class TestAppWait:
    def test_noop_without_target(self) -> None:
        class _App(App):
            name: ClassVar[str] = "stub"

        with patch("hallm.cli.subcommands.cluster.setup_builders.base.kubectl.wait") as mock_wait:
            _App().wait()
        mock_wait.assert_not_called()

    def test_waits_when_target_set(self) -> None:
        class _App(App):
            name: ClassVar[str] = "stub"
            wait_target: ClassVar[str | None] = "deploy/stub"
            wait_condition: ClassVar[WaitCondition] = WaitCondition.AVAILABLE
            wait_timeout: ClassVar[int] = 120

        with patch("hallm.cli.subcommands.cluster.setup_builders.base.kubectl.wait") as mock_wait:
            _App().wait()
        mock_wait.assert_called_once_with(
            "deploy/stub", "Available", namespace="default", timeout="120s"
        )


# ---------------------------------------------------------------------------
# Step defaults
# ---------------------------------------------------------------------------


class TestStepDefaults:
    def test_required_namespaces_from_app(self) -> None:
        class _NS(App):
            name: ClassVar[str] = "x"
            namespace: ClassVar[str] = "foo"

        class _S(Step):
            name: ClassVar[str] = "x"
            app: App | None = _NS()

        assert _S().required_namespaces == frozenset({"foo"})

    def test_required_namespaces_empty_without_app(self) -> None:
        class _S(Step):
            name: ClassVar[str] = "x"

        assert _S().required_namespaces == frozenset()

    def test_run_without_app_raises(self) -> None:
        class _S(Step):
            name: ClassVar[str] = "x"

        with pytest.raises(NotImplementedError):
            _S().run()

    def test_run_delegates_to_app(self) -> None:
        called: list[str] = []

        class _App(App):
            name: ClassVar[str] = "x"

            def install(self) -> None:
                called.append("installed")

        class _S(Step):
            name: ClassVar[str] = "x"
            app: App | None = _App()

        _S().run()
        assert called == ["installed"]

    def test_post_validate_calls_app_wait(self) -> None:
        called: list[str] = []

        class _App(App):
            name: ClassVar[str] = "x"

            def wait(self) -> None:
                called.append("waited")

        class _S(Step):
            name: ClassVar[str] = "x"
            app: App | None = _App()

        _S().post_validate()
        assert called == ["waited"]

    def test_lifecycle_phases_default_no_op(self) -> None:
        class _S(Step):
            name: ClassVar[str] = "x"

        s = _S()
        assert s.pre_validate() is None
        assert s.pre() is None
        assert s.post() is None
        assert s.post_validate() is None


# ---------------------------------------------------------------------------
# build_setup_pipeline
# ---------------------------------------------------------------------------


def _make_step(
    name: str,
    *,
    app_path: Path | None = None,
    app_namespace: str = "default",
    is_marker: bool = False,
    needs_secrets: bool = False,
) -> Step:
    """Build an ad-hoc Step (with optional App) for builder tests."""
    if app_path is not None:

        class _App(App):
            pass

        _App.name = f"{name}-app"
        _App.namespace = app_namespace
        _App.manifest_path = app_path
        app_instance: App | None = _App()
    else:
        app_instance = None

    class _Step(Step):
        def run(self) -> None:  # no-op so app-less stubs don't blow up
            if self.app is not None:
                self.app.install()

    _Step.name = name
    _Step.app = app_instance
    _Step.is_cluster_ready_marker = is_marker
    _Step.needs_secrets = needs_secrets
    return _Step()


class TestBuildSetupPipelineManifestClaim:
    def test_unclaimed_manifest_raises(self, fake_k8s: Path) -> None:
        # `fake_k8s` populates k8s/ with every required manifest. Build with no
        # Apps → all of them are unclaimed → builder raises.
        with pytest.raises(SetupStepError) as info:
            build_setup_pipeline([])
        assert "without a registered App" in str(info.value)

    def test_registries_yaml_ignored(self, fake_k8s: Path) -> None:
        # Sole remaining file = registries.yaml, which is excluded → build OK.
        for f in fake_k8s.glob("*.yaml"):
            if f.name != "registries.yaml":
                f.unlink()
        build_setup_pipeline([])  # no exception

    def test_subdirs_not_swept(self, fake_k8s: Path) -> None:
        # Clear top-level yamls (except registries) but keep test/ and adhoc/.
        for f in fake_k8s.glob("*.yaml"):
            if f.name != "registries.yaml":
                f.unlink()
        build_setup_pipeline([])  # subdir manifests don't count as unclaimed


class TestBuildSetupPipelineSynthesis:
    def test_namespace_step_inserted_after_marker(self, fake_k8s: Path) -> None:
        for f in fake_k8s.glob("*.yaml"):
            if f.name != "registries.yaml":
                f.unlink()
        marker = _make_step("api-ready", is_marker=True)
        tail = _make_step("post-tail")
        pipeline = build_setup_pipeline([marker, tail])

        # Inspect plan via the closure: invoke and capture echoed names.
        seen: list[str] = []

        def _record(step_name: str) -> None:
            seen.append(step_name)

        with (
            patch(
                "hallm.cli.subcommands.cluster.setup_builders.base.typer.echo",
                side_effect=lambda msg, **_kw: _record(msg),
            ),
            patch(
                "hallm.cli.subcommands.cluster.setup_builders.bootstrap_namespaces._run",
                return_value=_cp(),
            ),
        ):
            pipeline()

        # First echo is "api-ready", then "Bootstrapping namespaces", then "post-tail".
        names = [m for m in seen if m.startswith("\n==>")]
        assert "api-ready" in names[0]
        assert "Bootstrapping namespaces" in names[1]
        assert "post-tail" in names[2]

    def test_sync_secrets_inserted_once_before_first_consumer(self, fake_k8s: Path) -> None:
        for f in fake_k8s.glob("*.yaml"):
            if f.name != "registries.yaml":
                f.unlink()
        consumer1 = _make_step("uses-secrets-1", needs_secrets=True)
        consumer2 = _make_step("uses-secrets-2", needs_secrets=True)
        pipeline = build_setup_pipeline([consumer1, consumer2])

        seen: list[str] = []

        def _record(msg: str, **_kw: object) -> None:
            seen.append(msg)

        with (
            patch(
                "hallm.cli.subcommands.cluster.setup_builders.base.typer.echo",
                side_effect=_record,
            ),
            patch(
                "hallm.cli.subcommands.cluster.setup_builders.sync_secrets._secrets._sync_secrets"
            ),
        ):
            pipeline()

        names = [m for m in seen if m.startswith("\n==>")]
        # Order: "Syncing secrets", consumer1, consumer2 (no second sync)
        assert "Syncing secrets" in names[0]
        assert "uses-secrets-1" in names[1]
        assert "uses-secrets-2" in names[2]
        # Only one sync.
        assert sum("Syncing secrets" in n for n in names) == 1


class TestBuildSetupPipelineRollback:
    def test_failure_nukes_cluster_and_wraps(self, fake_k8s: Path) -> None:
        for f in fake_k8s.glob("*.yaml"):
            if f.name != "registries.yaml":
                f.unlink()

        class _Boom(Step):
            name: ClassVar[str] = "boom"

            def run(self) -> None:
                raise RuntimeError("kaboom")

        pipeline = build_setup_pipeline([_Boom()])

        with (
            patch("hallm.cli.subcommands.cluster.setup_builders.base._docker.run") as mock_docker,
            pytest.raises(SetupStepError) as info,
        ):
            pipeline()

        assert info.value.step_name == "boom"
        # Verify the nuke command issued.
        mock_docker.assert_called_once()
        cmd = mock_docker.call_args.args[0]
        assert cmd[:3] == ["k3d", "cluster", "delete"]

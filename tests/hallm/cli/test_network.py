"""Unit tests for hallm.cli.subcommands.network."""

import contextlib
from collections.abc import Callable
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from hallm.cli.subcommands import network
from hallm.cli.subcommands.network import app
from hallm.core.settings import settings
from tests.mocks import completed_process as _cp

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def network_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Temp network/ dir with the three repo files; patch module-level path constants."""
    nd = tmp_path / "network"
    nd.mkdir()
    caddyfile = nd / "Caddyfile"
    caddyfile.write_text("openclaw.hallm.local:80 {\n  reverse_proxy localhost:18789\n}\n")
    dnsmasq = nd / "dnsmasq.d"
    dnsmasq.write_text("address=/openclaw.hallm.local/127.0.0.2\n")
    unit_tpl = nd / "hallm-caddy.service.tpl"
    unit_tpl.write_text("ExecStart=##CADDY_BIN## run\n")

    monkeypatch.setattr(settings, "repo_root", tmp_path)
    monkeypatch.setattr(settings, "network_path", nd)
    return nd


def _socket_cm(*_args: object, **_kwargs: object) -> MagicMock:
    """create_connection side_effect that returns an open-socket context manager."""
    return MagicMock()


@contextlib.contextmanager
def _health_env(
    *,
    which: Callable[[str], str | None] = lambda b: f"/usr/bin/{b}",
    subprocess_calls: list[object] | None = None,
    file_matches: Callable[[Path, Path], bool] | bool = True,
    gethostbyname: Callable[[str], str] | str = "127.0.0.2",
    create_connection: Callable[..., object] = _socket_cm,
    conf_dir_set: bool = True,
    resolver_first: bool = True,
    dig_answer: str | None = "127.0.0.1",
) -> Iterator[None]:
    """Single context manager bundling every patch the health command touches."""
    if subprocess_calls is None:
        subprocess_calls = [_cp(), _cp()]  # systemctl is-active x2

    file_matches_kwargs = (
        {"side_effect": file_matches} if callable(file_matches) else {"return_value": file_matches}
    )
    gethost_kwargs = (
        {"side_effect": gethostbyname}
        if callable(gethostbyname)
        else {"return_value": gethostbyname}
    )

    with (
        patch("hallm.cli.subcommands.network.shutil.which", side_effect=which),
        patch("subprocess.run", side_effect=subprocess_calls),
        patch("hallm.cli.subcommands.network._file_matches", **file_matches_kwargs),
        patch("hallm.cli.subcommands.network.socket.gethostbyname", **gethost_kwargs),
        patch(
            "hallm.cli.subcommands.network.socket.create_connection",
            side_effect=create_connection,
        ),
        patch(
            "hallm.cli.subcommands.network._dnsmasq_conf_dir_set",
            return_value=conf_dir_set,
        ),
        patch(
            "hallm.cli.subcommands.network._resolver_first_in_resolv_conf",
            return_value=resolver_first,
        ),
        patch(
            "hallm.cli.subcommands.network._dig_at",
            return_value=dig_answer,
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


# Order of subprocess calls inside apply():
#   0  caddy validate
#   1  sudo install Caddyfile
#   2  sudo install dnsmasq.d
#   3  sudo sh -c "grep ... || echo ... >> /etc/dnsmasq.conf" (ensure conf-dir)
#   4  sudo install systemd unit
#   5  sudo systemctl daemon-reload
#   6  sudo systemctl enable --now hallm-caddy.service
#   7  sudo systemctl reload-or-restart hallm-caddy.service
#   8  sudo systemctl restart dnsmasq.service
#   9  nmcli -t -f NAME,DEVICE,TYPE c show --active  (empty stdout → no NM target)
_APPLY_HAPPY = [_cp()] * 9 + [_cp(stdout="")]


class TestApply:
    def test_success(self, network_dir: Path, runner: CliRunner) -> None:
        with (
            patch("hallm.cli.subcommands.network.shutil.which", return_value="/usr/bin/caddy"),
            patch("subprocess.run", side_effect=list(_APPLY_HAPPY)) as mock,
        ):
            result = runner.invoke(app, ["apply"])

        assert result.exit_code == 0
        assert "Network configuration applied" in result.output
        assert mock.call_count == 10
        validate_cmd = mock.call_args_list[0][0][0]
        assert validate_cmd[0] == "/usr/bin/caddy"
        assert "validate" in validate_cmd
        assert str(network_dir / "Caddyfile") in validate_cmd
        commands = [call[0][0] for call in mock.call_args_list]
        assert ["sudo", "systemctl", "restart", "dnsmasq.service"] in commands
        assert ["nmcli", "-t", "-f", "NAME,DEVICE,TYPE", "c", "show", "--active"] in commands

    def test_renders_unit_with_caddy_path(self, network_dir: Path, runner: CliRunner) -> None:
        captured: dict[str, str] = {}

        def _capture(cmd: list[str], **_kwargs: object) -> object:
            if cmd[:2] == ["sudo", "install"] and cmd[-1].endswith("hallm-caddy.service"):
                captured["unit"] = Path(cmd[-2]).read_text()
            return _cp()

        with (
            patch(
                "hallm.cli.subcommands.network.shutil.which",
                return_value="/home/linuxbrew/.linuxbrew/bin/caddy",
            ),
            patch("subprocess.run", side_effect=_capture),
        ):
            result = runner.invoke(app, ["apply"])

        assert result.exit_code == 0
        assert "/home/linuxbrew/.linuxbrew/bin/caddy" in captured["unit"]
        assert "##CADDY_BIN##" not in captured["unit"]

    @pytest.mark.parametrize("missing", ["Caddyfile", "dnsmasq.d", "hallm-caddy.service.tpl"])
    def test_missing_repo_file(self, network_dir: Path, runner: CliRunner, missing: str) -> None:
        (network_dir / missing).unlink()
        with patch("hallm.cli.subcommands.network.shutil.which", return_value="/usr/bin/caddy"):
            result = runner.invoke(app, ["apply"])

        assert result.exit_code == 1
        assert "Missing repo file" in result.output
        assert missing in result.output

    def test_missing_caddy_binary(self, network_dir: Path, runner: CliRunner) -> None:
        with patch("hallm.cli.subcommands.network.shutil.which", return_value=None):
            result = runner.invoke(app, ["apply"])

        assert result.exit_code == 1
        assert "'caddy' not found" in result.output

    @pytest.mark.parametrize(
        ("call_index", "expected_substring"),
        [
            (0, "Caddyfile failed validation"),
            (1, "Failed to install /etc/caddy/Caddyfile"),
            (2, "Failed to install /etc/dnsmasq.d/hallm.conf"),
            (3, "Failed to ensure conf-dir in /etc/dnsmasq.conf"),
            (4, "Failed to install /etc/systemd/system/hallm-caddy.service"),
            (5, "daemon-reload failed"),
            (6, "Failed to enable hallm-caddy.service"),
            (7, "Failed to reload hallm-caddy.service"),
            (8, "Failed to restart dnsmasq.service"),
        ],
    )
    def test_step_failures(
        self,
        network_dir: Path,
        runner: CliRunner,
        call_index: int,
        expected_substring: str,
    ) -> None:
        calls = list(_APPLY_HAPPY)
        calls[call_index] = _cp(returncode=1, stderr="boom")

        with (
            patch("hallm.cli.subcommands.network.shutil.which", return_value="/usr/bin/caddy"),
            patch("subprocess.run", side_effect=calls),
        ):
            result = runner.invoke(app, ["apply"])

        assert result.exit_code == 1
        assert expected_substring in result.output


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_all_checks_pass(self, network_dir: Path, runner: CliRunner) -> None:
        with _health_env():
            result = runner.invoke(app, ["health"])

        assert result.exit_code == 0
        assert "Network is healthy" in result.output
        assert "[FAIL]" not in result.output

    def test_caddy_binary_missing(self, network_dir: Path, runner: CliRunner) -> None:
        with _health_env(which=lambda b: None if b == "caddy" else f"/usr/bin/{b}"):
            result = runner.invoke(app, ["health"])

        assert result.exit_code == 1
        assert "[FAIL] caddy installed" in result.output

    def test_dnsmasq_binary_missing(self, network_dir: Path, runner: CliRunner) -> None:
        with _health_env(which=lambda b: None if b == "dnsmasq" else f"/usr/bin/{b}"):
            result = runner.invoke(app, ["health"])

        assert result.exit_code == 1
        assert "[FAIL] dnsmasq installed" in result.output

    def test_caddy_service_inactive(self, network_dir: Path, runner: CliRunner) -> None:
        # systemctl is-active returns 3 when the unit is inactive.
        with _health_env(subprocess_calls=[_cp(returncode=3), _cp()]):
            result = runner.invoke(app, ["health"])

        assert result.exit_code == 1
        assert "[FAIL] hallm-caddy.service active" in result.output

    def test_dnsmasq_service_inactive(self, network_dir: Path, runner: CliRunner) -> None:
        with _health_env(subprocess_calls=[_cp(), _cp(returncode=3)]):
            result = runner.invoke(app, ["health"])

        assert result.exit_code == 1
        assert "[FAIL] dnsmasq.service active" in result.output

    @pytest.mark.parametrize(
        ("system_path_attr", "label_substring"),
        [
            ("_SYSTEM_CADDYFILE", "matches network/Caddyfile"),
            ("_SYSTEM_DNSMASQ", "matches network/dnsmasq.d"),
        ],
    )
    def test_config_drift(
        self,
        network_dir: Path,
        runner: CliRunner,
        system_path_attr: str,
        label_substring: str,
    ) -> None:
        target = getattr(network, system_path_attr)

        def _matches(system_path: Path, _repo_path: Path) -> bool:
            return system_path != target

        with _health_env(file_matches=_matches):
            result = runner.invoke(app, ["health"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output
        assert label_substring in result.output

    def test_dns_wrong_ip(self, network_dir: Path, runner: CliRunner) -> None:
        with _health_env(gethostbyname="192.0.2.1"):
            result = runner.invoke(app, ["health"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output
        assert "openclaw.hallm.local resolves to" in result.output

    def test_dns_resolution_error(self, network_dir: Path, runner: CliRunner) -> None:
        def _raise(_host: str) -> str:
            raise OSError("nope")

        with _health_env(gethostbyname=_raise):
            result = runner.invoke(app, ["health"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output

    def test_tcp_unreachable(self, network_dir: Path, runner: CliRunner) -> None:
        def _refuse(*_args: object, **_kwargs: object) -> object:
            raise OSError("refused")

        with _health_env(create_connection=_refuse):
            result = runner.invoke(app, ["health"])

        assert result.exit_code == 1
        assert "[FAIL]" in result.output


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class TestNmActiveConnections:
    def test_nmcli_missing_returns_empty(self) -> None:
        with patch("hallm.cli.subcommands.network._run", return_value=_cp(returncode=1)):
            assert network._nm_active_connections() == []

    def test_parses_three_column_output(self) -> None:
        stdout = "Wired connection 1:enp42s0:802-3-ethernet\nbr0:br0:bridge\n"
        with patch("hallm.cli.subcommands.network._run", return_value=_cp(stdout=stdout)):
            conns = network._nm_active_connections()
        assert conns == [
            ("Wired connection 1", "enp42s0", "802-3-ethernet"),
            ("br0", "br0", "bridge"),
        ]

    def test_skips_malformed_lines(self) -> None:
        stdout = "good:dev:type\nshort:line\n"
        with patch("hallm.cli.subcommands.network._run", return_value=_cp(stdout=stdout)):
            conns = network._nm_active_connections()
        assert conns == [("good", "dev", "type")]


class TestEnsureNmDns:
    def test_nmcli_absent_warns_and_returns(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("hallm.cli.subcommands.network.shutil.which", return_value=None):
            network._ensure_nm_dns()
        captured = capsys.readouterr()
        assert "nmcli not on PATH" in captured.out

    def test_no_managed_targets_warns(self, capsys: pytest.CaptureFixture[str]) -> None:
        # Only bridge-type connection — should be skipped → empty targets.
        with (
            patch("hallm.cli.subcommands.network.shutil.which", return_value="/usr/bin/nmcli"),
            patch(
                "hallm.cli.subcommands.network._nm_active_connections",
                return_value=[("br0", "br0", "bridge")],
            ),
        ):
            network._ensure_nm_dns()
        captured = capsys.readouterr()
        assert "No active Ethernet/Wi-Fi" in captured.out

    def test_applies_to_ethernet_target(self) -> None:
        calls: list[list[str]] = []

        def _capture(cmd: list[str], **_kwargs: object) -> object:
            calls.append(cmd)
            return _cp()

        with (
            patch("hallm.cli.subcommands.network.shutil.which", return_value="/usr/bin/nmcli"),
            patch(
                "hallm.cli.subcommands.network._nm_active_connections",
                return_value=[("Wired connection 1", "enp42s0", "802-3-ethernet")],
            ),
            patch("subprocess.run", side_effect=_capture),
        ):
            network._ensure_nm_dns(resolver="127.0.0.1")

        modify = next(c for c in calls if "connection" in c and "modify" in c)
        assert modify[:5] == ["sudo", "nmcli", "connection", "modify", "Wired connection 1"]
        assert "ipv4.dns" in modify and "127.0.0.1" in modify
        reapply = next(c for c in calls if "device" in c and "reapply" in c)
        assert reapply == ["sudo", "nmcli", "device", "reapply", "enp42s0"]

    def test_reapply_failure_warns_but_does_not_raise(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # First subprocess call is the connection modify (success); second is the
        # device reapply which we simulate as failing.
        with (
            patch("hallm.cli.subcommands.network.shutil.which", return_value="/usr/bin/nmcli"),
            patch(
                "hallm.cli.subcommands.network._nm_active_connections",
                return_value=[("eth", "eth0", "802-3-ethernet")],
            ),
            patch("subprocess.run", side_effect=[_cp(), _cp(returncode=1)]),
        ):
            network._ensure_nm_dns()
        captured = capsys.readouterr()
        assert "reapply" in captured.out and "failed" in captured.out


class TestDnsmasqConfDirSet:
    def test_present(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        conf = tmp_path / "dnsmasq.conf"
        conf.write_text("# header\nconf-dir=/etc/dnsmasq.d/,*.conf\n")
        monkeypatch.setattr(network, "Path", lambda p: conf if "dnsmasq.conf" in p else Path(p))
        assert network._dnsmasq_conf_dir_set() is True

    def test_absent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        conf = tmp_path / "dnsmasq.conf"
        conf.write_text("# header only\n")
        monkeypatch.setattr(network, "Path", lambda p: conf if "dnsmasq.conf" in p else Path(p))
        assert network._dnsmasq_conf_dir_set() is False

    def test_file_missing_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Missing:
            def read_text(self) -> str:
                raise OSError("ENOENT")

        monkeypatch.setattr(network, "Path", lambda _p: _Missing())
        assert network._dnsmasq_conf_dir_set() is False


class TestResolverFirstInResolvConf:
    def test_first_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _R:
            def read_text(self) -> str:
                return "# comment\nnameserver 127.0.0.1\nnameserver 1.1.1.1\n"

        monkeypatch.setattr(network, "Path", lambda _p: _R())
        assert network._resolver_first_in_resolv_conf("127.0.0.1") is True

    def test_first_does_not_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _R:
            def read_text(self) -> str:
                return "nameserver 192.168.0.1\nnameserver 127.0.0.1\n"

        monkeypatch.setattr(network, "Path", lambda _p: _R())
        assert network._resolver_first_in_resolv_conf("127.0.0.1") is False

    def test_no_nameserver_entries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _R:
            def read_text(self) -> str:
                return "# only comments\n\n"

        monkeypatch.setattr(network, "Path", lambda _p: _R())
        assert network._resolver_first_in_resolv_conf("127.0.0.1") is False

    def test_file_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Missing:
            def read_text(self) -> str:
                raise OSError("ENOENT")

        monkeypatch.setattr(network, "Path", lambda _p: _Missing())
        assert network._resolver_first_in_resolv_conf("127.0.0.1") is False


class TestDigAt:
    def test_dig_missing_returns_none(self) -> None:
        with patch("hallm.cli.subcommands.network.shutil.which", return_value=None):
            assert network._dig_at("host.local", "127.0.0.1") is None

    def test_dig_rc_nonzero_returns_none(self) -> None:
        with (
            patch("hallm.cli.subcommands.network.shutil.which", return_value="/usr/bin/dig"),
            patch("hallm.cli.subcommands.network._run", return_value=_cp(returncode=1)),
        ):
            assert network._dig_at("host.local", "127.0.0.1") is None

    def test_empty_answer_returns_none(self) -> None:
        with (
            patch("hallm.cli.subcommands.network.shutil.which", return_value="/usr/bin/dig"),
            patch("hallm.cli.subcommands.network._run", return_value=_cp(stdout="\n")),
        ):
            assert network._dig_at("host.local", "127.0.0.1") is None

    def test_returns_first_answer(self) -> None:
        with (
            patch("hallm.cli.subcommands.network.shutil.which", return_value="/usr/bin/dig"),
            patch(
                "hallm.cli.subcommands.network._run",
                return_value=_cp(stdout="127.0.0.1\n"),
            ),
        ):
            assert network._dig_at("host.local", "127.0.0.1") == "127.0.0.1"


class TestFileMatches:
    def test_matches(self, tmp_path: Path) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.write_text("same")
        b.write_text("same")
        assert network._file_matches(a, b) is True

    def test_differs(self, tmp_path: Path) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.write_text("one")
        b.write_text("two")
        assert network._file_matches(a, b) is False

    def test_missing_returns_false(self, tmp_path: Path) -> None:
        b = tmp_path / "b"
        b.write_text("x")
        assert network._file_matches(tmp_path / "missing", b) is False

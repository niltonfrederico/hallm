"""SigNoz observability install (helm) — gated by SIGNOZ_ENABLED."""

from typing import ClassVar

from hallm.cli.subcommands import signoz as _signoz
from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step


class SignozApp(App):
    """No manifest_path: SigNoz install is helm-driven inside _run_bootstrap.

    The signoz-extras.yaml and signoz-ingress.yaml manifests live under
    k8s/archived/ when the feature flag is off, so they don't trip the
    builder's manifest-claim check.
    """

    name: ClassVar[str] = "SigNoz"
    namespace: ClassVar[str] = "signoz"

    def install(self) -> None:
        _signoz._run_bootstrap()


class SignozStep(Step):
    name: ClassVar[str] = "Bootstrapping SigNoz"
    app: App = SignozApp()

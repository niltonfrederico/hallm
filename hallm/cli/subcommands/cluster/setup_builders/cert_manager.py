"""cert-manager install via upstream URL manifest."""

from typing import ClassVar

from hallm.cli.subcommands.cluster.setup_builders.base import App
from hallm.cli.subcommands.cluster.setup_builders.base import Step
from hallm.cli.subcommands.cluster.setup_builders.base import WaitCondition
from hallm.core.settings import ClusterSettings


class CertManagerApp(App):
    name: ClassVar[str] = "cert-manager"
    namespace: ClassVar[str] = "cert-manager"
    manifest_url: ClassVar[str | None] = ClusterSettings.CERT_MANAGER_URL
    wait_target: ClassVar[str | None] = "deploy/cert-manager-webhook"
    wait_condition: ClassVar[WaitCondition] = WaitCondition.AVAILABLE
    wait_timeout: ClassVar[int] = 120


class CertManagerStep(Step):
    name: ClassVar[str] = "Installing cert-manager"
    app: App = CertManagerApp()

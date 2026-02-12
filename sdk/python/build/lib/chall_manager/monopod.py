"""ExposedMonopod scenario implementation."""

from typing import Optional
from dataclasses import dataclass

from .base import Scenario, ScenarioConfig, ValidationError
from .containers import Container


@dataclass
class MonopodConfig(ScenarioConfig):
    """Configuration for Monopod scenario."""

    container: Optional[Container] = None


class MonopodScenario(Scenario):
    """
    Single container scenario.

    Best for simple challenges with a single service.
    """

    def __init__(self, config: MonopodConfig):
        super().__init__(config)
        self.monopod_config = config

    def validate(self) -> None:
        """Validate monopod configuration."""
        if not self.monopod_config.container:
            raise ValidationError("Monopod scenario requires a container")

        self.monopod_config.container.validate()

    def generate_pulumi_code(self) -> str:
        """Generate Pulumi Python code for Monopod scenario."""
        container = self.monopod_config.container
        code_parts = []

        # Imports
        code_parts.append(self._generate_common_imports())
        code_parts.append(self._generate_sdk_imports())
        code_parts.append(self._generate_config_loading())

        # Labels
        code_parts.append("""
# Standard labels
labels = {
    "app.kubernetes.io/name": identity,
    "app.kubernetes.io/component": "chall-manager",
    "app.kubernetes.io/part-of": "chall-manager",
    "chall-manager.ctfer.io/identity": identity,
}
""")

        # Namespace
        code_parts.append(self._generate_namespace())

        # ConfigMap for files if needed
        if container.files:
            code_parts.append(self._generate_files_configmap(container))

        # Container spec
        code_parts.append(self._generate_container_spec(container))

        # Deployment
        code_parts.append(self._generate_deployment(container))

        # Service
        code_parts.append(self._generate_service(container))

        # Ingress if needed
        if any(p.expose_type.value == "ingress" for p in container.ports):
            code_parts.append(self._generate_ingress(container))

        code_parts.append(self._generate_footer())

        return "\n".join(code_parts)

    def _generate_files_configmap(
        self, container: Container, var_prefix: str = ""
    ) -> str:
        """Generate ConfigMap for container files."""
        # Use the base class method with no prefix for monopod
        return super()._generate_files_configmap(container, var_prefix="")

    def _generate_container_spec(self, container: Container) -> str:
        """Generate the main container specification."""
        lines = ["# Main container", "main_container = {"]
        lines.append(f'    "name": "{container.name}",')
        lines.append(f'    "image": "{container.image}",')

        # Ports
        lines.append('    "ports": [')
        for p in container.ports:
            lines.append(
                f'        {{"containerPort": {p.port}, "protocol": "{p.protocol}"}},'
            )
        lines.append("    ],")

        # Environment variables
        if container.envs:
            lines.append('    "env": [')
            for k, v in container.envs.items():
                # Use repr() to properly escape the value and prevent code injection
                lines.append(f'        {{"name": {repr(k)}, "value": {repr(v)}}},')
            lines.append("    ],")

        # Resources
        if container.limit_cpu or container.limit_memory:
            limits = []
            if container.limit_cpu:
                limits.append(f'"cpu": "{container.limit_cpu}"')
            if container.limit_memory:
                limits.append(f'"memory": "{container.limit_memory}"')
            lines.append(f'    "resources": {{"limits": {{{", ".join(limits)}}}}},')

        # Volume mounts
        if container.files:
            lines.append('    "volumeMounts": [')
            for path in container.files.keys():
                sub_path = path.lstrip("/").replace("/", "-")
                lines.append(
                    f'        {{"name": "files", "mountPath": "{path}", "subPath": "{sub_path}"}},'
                )
            lines.append("    ],")

        lines.append("}")
        lines.append("")

        return "\n".join(lines)

    def _generate_deployment(self, container: Container) -> str:
        """Generate Deployment resource."""
        lines = ["# Deployment", "deployment = k8s.apps.v1.Deployment("]
        lines.append('    "deployment",')
        lines.append("    metadata=k8s.meta.v1.ObjectMetaArgs(")
        lines.append('        name=f"{identity}-deployment",')
        lines.append("        namespace=ns.metadata.name,")
        lines.append("    ),")
        lines.append("    spec=k8s.apps.v1.DeploymentSpecArgs(")
        lines.append("        replicas=1,")
        lines.append(
            "        selector=k8s.meta.v1.LabelSelectorArgs(match_labels=labels),"
        )
        lines.append("        template=k8s.core.v1.PodTemplateSpecArgs(")
        lines.append("            metadata=k8s.meta.v1.ObjectMetaArgs(labels=labels),")
        lines.append("            spec=k8s.core.v1.PodSpecArgs(")
        lines.append("                automount_service_account_token=False,")

        # Share process namespace for packet capture
        share_process = (
            "True"
            if (container.packet_capture and self.config.packet_capture_pvc)
            else "False"
        )
        lines.append(f"                share_process_namespace={share_process},")
        lines.append("                containers=[main_container],")

        # Volumes
        volumes = []
        if container.files:
            volumes.append("{")
            volumes.append('                    "name": "files",')
            volumes.append(
                '                    "configMap": {"name": files_configmap.metadata.name},'
            )
            volumes.append("                }")

        if container.packet_capture and self.config.packet_capture_pvc:
            volumes.append("{")
            volumes.append('                    "name": "packet-captures",')
            volumes.append(
                f'                    "persistentVolumeClaim": {{"claimName": "{self.config.packet_capture_pvc}"}},'
            )
            volumes.append("                }")
            volumes.append("{")
            volumes.append('                    "name": "capture-script",')
            volumes.append(
                '                    "configMap": {"name": "pcap-script", "defaultMode": 0o755},'
            )
            volumes.append("                }")

        if volumes:
            lines.append("                volumes=[")
            for vol in volumes:
                lines.append(f"                {vol},")
            lines.append("                ],")

        lines.append("            ),")
        lines.append("        ),")
        lines.append("    ),")
        lines.append("    opts=ResourceOptions(depends_on=[ns]),")
        lines.append(")")
        lines.append("")

        return "\n".join(lines)

    def _generate_service(self, container: Container) -> str:
        """Generate Service resource."""
        lines = ["# Service", "service = k8s.core.v1.Service("]
        lines.append('    "service",')
        lines.append("    metadata=k8s.meta.v1.ObjectMetaArgs(")
        lines.append('        name=f"{identity}-service",')
        lines.append("        namespace=ns.metadata.name,")
        lines.append("    ),")
        lines.append("    spec=k8s.core.v1.ServiceSpecArgs(")

        # Service type
        svc_type = "ClusterIP"
        for p in container.ports:
            if p.expose_type.value in ("NodePort", "LoadBalancer"):
                svc_type = p.expose_type.value
                break
        lines.append(f'        type="{svc_type}",')
        lines.append("        selector=labels,")
        lines.append("        ports=[")

        for p in container.ports:
            lines.append(
                f'            {{"port": {p.port}, "targetPort": {p.port}, "protocol": "{p.protocol}"}},'
            )

        lines.append("        ],")
        lines.append("    ),")
        lines.append("    opts=ResourceOptions(depends_on=[deployment]),")
        lines.append(")")
        lines.append("")

        return "\n".join(lines)

    def _generate_ingress(self, container: Container) -> str:
        """Generate Ingress resource."""
        ingress_ports = [p for p in container.ports if p.expose_type.value == "ingress"]
        if not ingress_ports:
            return ""

        lines = ["# Ingress", "ingress = k8s.networking.v1.Ingress("]
        lines.append('    "ingress",')
        lines.append("    metadata=k8s.meta.v1.ObjectMetaArgs(")
        lines.append('        name=f"{identity}-ingress",')
        lines.append("        namespace=ns.metadata.name,")
        lines.append("        annotations={")
        lines.append('            "nginx.ingress.kubernetes.io/ssl-redirect": "false",')
        lines.append("        },")
        lines.append("    ),")
        lines.append("    spec=k8s.networking.v1.IngressSpecArgs(")
        lines.append("        rules=[")

        for port in ingress_ports:
            host = f"{port.port}.{{identity}}.{self.config.hostname or 'example.com'}"
            lines.append("            k8s.networking.v1.IngressRuleArgs(")
            lines.append(f'                host="{host}",')
            lines.append(
                "                http=k8s.networking.v1.HTTPIngressRuleValueArgs("
            )
            lines.append("                    paths=[")
            lines.append(
                "                        k8s.networking.v1.HTTPIngressPathArgs("
            )
            lines.append('                            path="/",')
            lines.append('                            path_type="Prefix",')
            lines.append(
                "                            backend=k8s.networking.v1.IngressBackendArgs("
            )
            lines.append(
                "                                service=k8s.networking.v1.IngressServiceBackendArgs("
            )
            lines.append(
                "                                    name=service.metadata.name,"
            )
            lines.append(
                "                                    port=k8s.networking.v1.ServiceBackendPortArgs("
            )
            lines.append(f"                                        number={port.port},")
            lines.append("                                    ),")
            lines.append("                                ),")
            lines.append("                            ),")
            lines.append("                        ),")
            lines.append("                    ],")
            lines.append("                ),")
            lines.append("            ),")

        lines.append("        ],")
        lines.append("    ),")
        lines.append("    opts=ResourceOptions(depends_on=[service]),")
        lines.append(")")
        lines.append("")

        return "\n".join(lines)

    def _generate_footer(self) -> str:
        """Generate footer with connection info export."""
        return """
# Export outputs
pulumi.export("connection_info", service.status.load_balancer.ingress.apply(
    lambda ingress: f"http://{ingress[0].ip}" if ingress else "pending"
))
"""


# Backwards compatibility
ExposedMonopodScenario = MonopodScenario

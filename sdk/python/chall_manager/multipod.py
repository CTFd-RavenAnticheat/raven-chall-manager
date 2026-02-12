"""ExposedMultipod scenario implementation."""

from typing import List, Dict, Optional
from dataclasses import dataclass, field

from .base import Scenario, ScenarioConfig, ValidationError
from .containers import Container, Rule


@dataclass
class MultipodConfig(ScenarioConfig):
    """Configuration for Multipod scenario."""

    containers: Dict[str, Container] = field(default_factory=dict)
    rules: List[Rule] = field(default_factory=list)


class MultipodScenario(Scenario):
    """
    Multi-container scenario.

    Best for complex challenges with multiple services that need to communicate.
    """

    def __init__(self, config: MultipodConfig):
        super().__init__(config)
        self.multipod_config = config

    def validate(self) -> None:
        """Validate multipod configuration."""
        if not self.multipod_config.containers:
            raise ValidationError("Multipod scenario requires at least one container")

        for name, container in self.multipod_config.containers.items():
            if container.name != name:
                raise ValidationError(
                    f"Container key '{name}' must match container name '{container.name}'"
                )
            container.validate()

        for rule in self.multipod_config.rules:
            rule.validate()
            if rule.from_container not in self.multipod_config.containers:
                raise ValidationError(
                    f"Rule references unknown container: {rule.from_container}"
                )
            if rule.to_container not in self.multipod_config.containers:
                raise ValidationError(
                    f"Rule references unknown container: {rule.to_container}"
                )

    def generate_pulumi_code(self) -> str:
        """Generate Pulumi Python code for Multipod scenario."""
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

        # ConfigMaps for files
        for container in self.multipod_config.containers.values():
            if container.files:
                code_parts.append(self._generate_files_configmap(container))

        # Deployments and Services
        for name, container in self.multipod_config.containers.items():
            code_parts.append(self._generate_container_deployment(name, container))
            code_parts.append(self._generate_container_service(name, container))

        # NetworkPolicy for rules
        if self.multipod_config.rules:
            code_parts.append(self._generate_network_policies())

        code_parts.append(self._generate_footer())

        return "\n".join(code_parts)

    def _generate_files_configmap(
        self, container: Container, var_prefix: str = ""
    ) -> str:
        """Generate ConfigMap for container files."""
        # Use the base class method with container name as prefix for multipod
        return super()._generate_files_configmap(container, var_prefix=container.name)

    def _generate_container_deployment(self, name: str, container: Container) -> str:
        """Generate Deployment for a container."""
        lines = [
            f"# Deployment for {name}",
            f"{name}_deployment = k8s.apps.v1.Deployment(",
        ]
        lines.append(f'    "{name}-deployment",')
        lines.append("    metadata=k8s.meta.v1.ObjectMetaArgs(")
        lines.append(f'        name=f"{{identity}}-{name}-deployment",')
        lines.append("        namespace=ns.metadata.name,")
        lines.append("    ),")
        lines.append("    spec=k8s.apps.v1.DeploymentSpecArgs(")
        lines.append("        replicas=1,")
        lines.append(
            '        selector=k8s.meta.v1.LabelSelectorArgs(match_labels={**labels, "component": "'
            + name
            + '"}),'
        )
        lines.append("        template=k8s.core.v1.PodTemplateSpecArgs(")
        lines.append("            metadata=k8s.meta.v1.ObjectMetaArgs(")
        lines.append('                labels={**labels, "component": "' + name + '"},')
        lines.append("            ),")
        lines.append("            spec=k8s.core.v1.PodSpecArgs(")
        lines.append("                automount_service_account_token=False,")

        # Share process namespace for packet capture
        if container.packet_capture and self.config.packet_capture_pvc:
            lines.append("                share_process_namespace=True,")
        else:
            lines.append("                share_process_namespace=False,")

        # Containers
        lines.append("                containers=[")
        lines.append("                    {")
        lines.append(f'                        "name": "{container.name}",')
        lines.append(f'                        "image": "{container.image}",')

        # Ports
        if container.ports:
            lines.append('                        "ports": [')
            for p in container.ports:
                lines.append(
                    f'                            {{"containerPort": {p.port}, "protocol": "{p.protocol}"}},'
                )
            lines.append("                        ],")

        # Environment
        if container.envs:
            lines.append('                        "env": [')
            for k, v in container.envs.items():
                # Use repr() to properly escape the value and prevent code injection
                lines.append(
                    f'                            {{"name": {repr(k)}, "value": {repr(v)}}},'
                )
            lines.append("                        ],")

        # Resources
        if container.limit_cpu or container.limit_memory:
            limits = []
            if container.limit_cpu:
                limits.append(f'"cpu": "{container.limit_cpu}"')
            if container.limit_memory:
                limits.append(f'"memory": "{container.limit_memory}"')
            lines.append(
                f'                        "resources": {{"limits": {{{", ".join(limits)}}}}},'
            )

        # Volume mounts
        if container.files:
            lines.append('                        "volumeMounts": [')
            for path in container.files.keys():
                sub_path = path.lstrip("/").replace("/", "-")
                lines.append(
                    f'                            {{"name": "files", "mountPath": "{path}", "subPath": "{sub_path}"}},'
                )
            lines.append("                        ],")

        lines.append("                    },")
        lines.append("                ],")

        # Volumes
        volumes = []
        if container.files:
            volumes.append("                    {")
            volumes.append('                        "name": "files",')
            volumes.append(
                f'                        "configMap": {{"name": {container.name}_files_configmap.metadata.name}},'
            )
            volumes.append("                    },")

        if container.packet_capture and self.config.packet_capture_pvc:
            volumes.append("                    {")
            volumes.append('                        "name": "packet-captures",')
            volumes.append(
                f'                        "persistentVolumeClaim": {{"claimName": "{self.config.packet_capture_pvc}"}},'
            )
            volumes.append("                    },")
            volumes.append("                    {")
            volumes.append('                        "name": "capture-script",')
            volumes.append(
                '                        "configMap": {"name": "pcap-script", "defaultMode": 0o755},'
            )
            volumes.append("                    },")

        if volumes:
            lines.append("                volumes=[")
            for vol in volumes:
                lines.append(vol)
            lines.append("                ],")

        lines.append("            ),")
        lines.append("        ),")
        lines.append("    ),")
        lines.append("    opts=ResourceOptions(depends_on=[ns]),")
        lines.append(")")
        lines.append("")

        return "\n".join(lines)

    def _generate_container_service(self, name: str, container: Container) -> str:
        """Generate Service for a container."""
        if not container.ports:
            return ""

        lines = [f"# Service for {name}", f"{name}_service = k8s.core.v1.Service("]
        lines.append(f'    "{name}-service",')
        lines.append("    metadata=k8s.meta.v1.ObjectMetaArgs(")
        lines.append(f'        name=f"{{identity}}-{name}-service",')
        lines.append("        namespace=ns.metadata.name,")
        lines.append("    ),")
        lines.append("    spec=k8s.core.v1.ServiceSpecArgs(")

        # Determine service type
        svc_type = "ClusterIP"
        for p in container.ports:
            if p.expose_type.value in ("NodePort", "LoadBalancer"):
                svc_type = p.expose_type.value
                break
        lines.append(f'        type="{svc_type}",')
        lines.append('        selector={**labels, "component": "' + name + '"},')
        lines.append("        ports=[")

        for p in container.ports:
            lines.append(
                f'            {{"port": {p.port}, "targetPort": {p.port}, "protocol": "{p.protocol}"}},'
            )

        lines.append("        ],")
        lines.append("    ),")
        lines.append(f"    opts=ResourceOptions(depends_on=[{name}_deployment]),")
        lines.append(")")
        lines.append("")

        return "\n".join(lines)

    def _generate_network_policies(self) -> str:
        """Generate NetworkPolicies for inter-container rules."""
        lines = ["# Network Policies for inter-container communication"]

        for i, rule in enumerate(self.multipod_config.rules):
            policy_name = f"allow-{rule.from_container}-to-{rule.to_container}"
            lines.append(f"{policy_name}_policy = k8s.networking.v1.NetworkPolicy(")
            lines.append(f'    "{policy_name}",')
            lines.append("    metadata=k8s.meta.v1.ObjectMetaArgs(")
            lines.append(f'        name="{policy_name}",')
            lines.append("        namespace=ns.metadata.name,")
            lines.append("    ),")
            lines.append("    spec=k8s.networking.v1.NetworkPolicySpecArgs(")
            lines.append("        pod_selector=k8s.meta.v1.LabelSelectorArgs(")
            lines.append(
                '            match_labels={"component": "' + rule.to_container + '"},'
            )
            lines.append("        ),")
            lines.append('        policy_types=["Ingress"],')
            lines.append("        ingress=[")
            lines.append("            k8s.networking.v1.NetworkPolicyIngressRuleArgs(")
            lines.append("                from_=[")
            lines.append("                    k8s.networking.v1.NetworkPolicyPeerArgs(")
            lines.append(
                "                        pod_selector=k8s.meta.v1.LabelSelectorArgs("
            )
            lines.append(
                '                            match_labels={"component": "'
                + rule.from_container
                + '"},'
            )
            lines.append("                        ),")
            lines.append("                    ),")
            lines.append("                ],")

            if rule.ports:
                lines.append("                ports=[")
                for port in rule.ports:
                    lines.append(
                        f"                    k8s.networking.v1.NetworkPolicyPortArgs("
                    )
                    lines.append(f"                        port={port},")
                    lines.append(f'                        protocol="{rule.protocol}",')
                    lines.append("                    ),")
                lines.append("                ],")

            lines.append("            ),")
            lines.append("        ],")
            lines.append("    ),")
            lines.append("    opts=ResourceOptions(depends_on=[ns]),")
            lines.append(")")
            lines.append("")

        return "\n".join(lines)

    def _generate_footer(self) -> str:
        """Generate footer with connection info export."""
        # Use the first container's service for connection info
        first_container = list(self.multipod_config.containers.keys())[0]
        return f"""
# Export outputs
pulumi.export("connection_info", {first_container}_service.status.load_balancer.ingress.apply(
    lambda ingress: f"http://{{ingress[0].ip}}" if ingress else "pending"
))
"""


# Backwards compatibility
ExposedMultipodScenario = MultipodScenario

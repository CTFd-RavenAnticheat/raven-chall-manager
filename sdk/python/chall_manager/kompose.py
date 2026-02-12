"""Kompose scenario implementation."""

from typing import Dict, List, Optional
from dataclasses import dataclass, field

from .base import Scenario, ScenarioConfig, ValidationError
from .containers import PortBinding


@dataclass
class KomposeConfig(ScenarioConfig):
    """Configuration for Kompose scenario."""

    yaml_content: str = ""
    ports: Dict[str, List[PortBinding]] = field(default_factory=dict)
    packet_capture: Dict[str, bool] = field(default_factory=dict)


class KomposeScenario(Scenario):
    """
    Docker Compose to Kubernetes scenario.

    Best for existing Docker Compose setups.
    """

    def __init__(self, config: KomposeConfig):
        super().__init__(config)
        self.kompose_config = config

    def validate(self) -> None:
        """Validate kompose configuration."""
        if not self.kompose_config.yaml_content:
            raise ValidationError("Kompose scenario requires YAML content")

        # Validate packet_capture keys match service names
        for service_name in self.kompose_config.packet_capture.keys():
            if service_name not in self.kompose_config.ports:
                raise ValidationError(
                    f"Packet capture specified for unknown service: {service_name}"
                )

    def generate_pulumi_code(self) -> str:
        """Generate Pulumi Python code for Kompose scenario."""
        code_parts = []

        # Imports
        code_parts.append(self._generate_common_imports())
        code_parts.append(self._generate_sdk_imports())
        code_parts.append(self._generate_config_loading())

        # Additional imports for YAML processing
        code_parts.append("""
import yaml
import tempfile
import os
""")

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

        # ConfigMap for packet capture script if needed
        if any(self.kompose_config.packet_capture.values()):
            code_parts.append(self._generate_packet_capture_configmap())

        # Docker Compose YAML processing
        code_parts.append(self._generate_yaml_processing())

        # Deployments and Services from YAML
        code_parts.append(self._generate_kompose_resources())

        code_parts.append(self._generate_footer())

        return "\n".join(code_parts)

    def _generate_packet_capture_configmap(self) -> str:
        """Generate ConfigMap for packet capture daemon script."""
        return '''
# ConfigMap for packet capture daemon script
pcap_script_configmap = k8s.core.v1.ConfigMap(
    "pcap-script",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="pcap-script",
        namespace=ns.metadata.name,
    ),
    data={
        "capture-daemon.sh": """#!/bin/bash
# Packet capture daemon script
set -e

PORTS="${PORTS:-}"
CAPTURE_DIR="${CAPTURE_DIR:-/captures}"
CONTAINER_NAME="${CONTAINER_NAME:-}"

echo "Starting packet capture daemon for $CONTAINER_NAME"
echo "Ports: $PORTS"
echo "Capture dir: $CAPTURE_DIR"

# Create capture directory
mkdir -p "$CAPTURE_DIR"

# Parse ports and start tcpdump for each
IFS=',' read -ra PORT_ARRAY <<< "$PORTS"
for port_proto in "${PORT_ARRAY[@]}"; do
    if [ -z "$port_proto" ]; then
        continue
    fi
    
    IFS=':' read -r port proto <<< "$port_proto"
    proto="${proto:-tcp}"
    
    echo "Starting capture for port $port ($proto)"
    
    # Start tcpdump in background
    tcpdump -i any -w "$CAPTURE_DIR/$port-$proto.pcap" \
        "${proto} port $port" &
done

# Wait for all background processes
wait
""",
    },
    opts=ResourceOptions(depends_on=[ns]),
)
'''

    def _generate_yaml_processing(self) -> str:
        """Generate code to process Docker Compose YAML."""
        # Use repr() to safely escape the YAML content and prevent injection
        # repr() properly handles all special characters including triple quotes
        yaml_repr = repr(self.kompose_config.yaml_content)

        return f"""
# Docker Compose YAML content
compose_yaml = {yaml_repr}

# Parse YAML to extract services
try:
    compose_config = yaml.safe_load(compose_yaml)
    if not isinstance(compose_config, dict):
        raise ValueError(f"Invalid Docker Compose YAML: expected dict, got {{type(compose_config).__name__}}")
    services = compose_config.get('services', {{}})
    if not isinstance(services, dict):
        raise ValueError(f"Invalid 'services' in Docker Compose YAML: expected dict, got {{type(services).__name__}}")
except yaml.YAMLError as e:
    raise ValueError(f"Failed to parse Docker Compose YAML: {{e}}")
"""

    def _generate_kompose_resources(self) -> str:
        """Generate Kubernetes resources from Docker Compose."""
        lines = ["# Generate Kubernetes resources from Docker Compose"]

        # Create deployments for each service
        lines.append("""
for service_name, service_config in services.items():
    # Get image
    image = service_config.get('image', '')
    
    # Get ports
    service_ports = service_config.get('ports', [])
    
    # Build container spec
    container = {
        "name": service_name,
        "image": image,
        "ports": [],
    }
    
    for port_mapping in service_ports:
        # Parse port mapping (e.g., "8080:80" or "80")
        if ':' in str(port_mapping):
            host_port, container_port = str(port_mapping).split(':')
        else:
            container_port = str(port_mapping)
        
        container["ports"].append({
            "containerPort": int(container_port),
            "protocol": "TCP",
        })
    
    # Get environment variables
    env = service_config.get('environment', {})
    if env:
        container["env"] = []
        if isinstance(env, dict):
            for k, v in env.items():
                container["env"].append({"name": k, "value": str(v)})
        elif isinstance(env, list):
            for item in env:
                if '=' in item:
                    k, v = item.split('=', 1)
                    container["env"].append({"name": k, "value": v})
    
    # Get volumes
    volumes = service_config.get('volumes', [])
    if volumes:
        container["volumeMounts"] = []
        for vol in volumes:
            if ':' in vol:
                host_path, container_path = vol.split(':', 1)
                container["volumeMounts"].append({
                    "name": "data",
                    "mountPath": container_path,
                })
""")

        # Add packet capture sidecar if enabled for this service
        lines.append(
            """
    # Check if packet capture is enabled for this service
    packet_capture_enabled = """
            + repr(self.kompose_config.packet_capture)
            + """.get(service_name, False)
    
    containers = [container]
    pod_volumes = []
    
    if packet_capture_enabled and """
            + (
                '"' + self.config.packet_capture_pvc + '"'
                if self.config.packet_capture_pvc
                else '"pcap-core"'
            )
            + """:
        # Add packet capture sidecar
        port_list = ",".join([f"{p['containerPort']}:tcp" for p in container["ports"]])
        
        pcap_sidecar = {
            "name": f"{service_name}-pcap",
            "image": "nicolaka/netshoot:v0.13",
            "imagePullPolicy": "IfNotPresent",
            "command": ["/bin/bash", "/scripts/capture-daemon.sh"],
            "env": [
                {"name": "CONTAINER_NAME", "value": service_name},
                {"name": "IDENTITY", "value": identity},
                {"name": "PORTS", "value": port_list},
                {"name": "CAPTURE_DIR", "value": "/captures"},
            ],
            "securityContext": {
                "privileged": True,
                "runAsUser": 0,
                "capabilities": {"add": ["NET_RAW", "NET_ADMIN"]},
            },
            "volumeMounts": [
                {"name": "packet-captures", "mountPath": "/captures", "subPath": f"captures/{identity}/{service_name}"},
                {"name": "capture-script", "mountPath": "/scripts", "readOnly": True},
            ],
            "resources": {
                "limits": {"cpu": "200m", "memory": "256Mi"},
                "requests": {"cpu": "100m", "memory": "128Mi"},
            },
        }
        containers.append(pcap_sidecar)
        
        # Add volumes for packet capture
        pod_volumes.extend([
            {"name": "packet-captures", "persistentVolumeClaim": {"claimName": """
            + (
                '"' + self.config.packet_capture_pvc + '"'
                if self.config.packet_capture_pvc
                else '"pcap-core"'
            )
            + """}},
            {"name": "capture-script", "configMap": {"name": "pcap-script", "defaultMode": 0o755}},
        ])
"""
        )

        # Create deployment
        lines.append("""
    # Create Deployment
    deployment = k8s.apps.v1.Deployment(
        f"{service_name}-deployment",
        metadata=k8s.meta.v1.ObjectMetaArgs(
            name=f"{identity}-{service_name}",
            namespace=ns.metadata.name,
        ),
        spec=k8s.apps.v1.DeploymentSpecArgs(
            replicas=1,
            selector=k8s.meta.v1.LabelSelectorArgs(match_labels={**labels, "service": service_name}),
            template=k8s.core.v1.PodTemplateSpecArgs(
                metadata=k8s.meta.v1.ObjectMetaArgs(
                    labels={**labels, "service": service_name},
                ),
                spec=k8s.core.v1.PodSpecArgs(
                    automount_service_account_token=False,
                    share_process_namespace=packet_capture_enabled,
                    containers=containers,
                    volumes=pod_volumes if pod_volumes else None,
                ),
            ),
        ),
        opts=ResourceOptions(depends_on=[ns]),
    )
""")

        # Create service
        lines.append("""
    # Create Service if ports are exposed
    if container["ports"]:
        k8s.core.v1.Service(
            f"{service_name}-service",
            metadata=k8s.meta.v1.ObjectMetaArgs(
                name=f"{identity}-{service_name}",
                namespace=ns.metadata.name,
            ),
            spec=k8s.core.v1.ServiceSpecArgs(
                selector={**labels, "service": service_name},
                ports=[
                    {"port": p["containerPort"], "targetPort": p["containerPort"]}
                    for p in container["ports"]
                ],
            ),
            opts=ResourceOptions(depends_on=[deployment]),
        )
""")

        return "\n".join(lines)

    def _generate_footer(self) -> str:
        """Generate footer with connection info export."""
        return """
# Export outputs
pulumi.export("connection_info", pulumi.Output.from_input("Docker Compose deployment complete"))
"""


# Backwards compatibility
DockerComposeScenario = KomposeScenario

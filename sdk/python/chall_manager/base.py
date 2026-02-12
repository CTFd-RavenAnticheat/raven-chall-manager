"""Base classes for chall-manager scenarios."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import os
import re


@dataclass
class ScenarioConfig:
    """Base configuration for all scenario types."""

    identity: str
    challenge_id: str
    hostname: str = ""
    label: Optional[str] = None
    from_cidr: str = "0.0.0.0/0"
    ingress_namespace: str = ""
    ingress_labels: Dict[str, str] = field(default_factory=dict)
    ingress_annotations: Dict[str, str] = field(default_factory=dict)
    image_pull_secrets: List[str] = field(default_factory=list)
    packet_capture_pvc: Optional[str] = None

    def __post_init__(self):
        """Validate configuration after initialization."""
        self._validate_kubernetes_name(self.identity, "identity")
        self._validate_kubernetes_name(self.challenge_id, "challenge_id")
        if self.hostname:
            self._validate_hostname(self.hostname)
        if self.from_cidr:
            self._validate_cidr(self.from_cidr)
        if self.label:
            self._validate_label(self.label)

    @staticmethod
    def _validate_kubernetes_name(value: str, field_name: str) -> None:
        """Validate Kubernetes DNS-1123 subdomain name."""
        if not value:
            raise ValidationError(f"{field_name} cannot be empty")
        if len(value) > 63:
            raise ValidationError(
                f"{field_name} must be 63 characters or less (got {len(value)})"
            )
        if not re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", value):
            raise ValidationError(
                f"{field_name} must consist of lowercase alphanumeric characters or '-', "
                f"start and end with an alphanumeric character (got: {value})"
            )

    @staticmethod
    def _validate_hostname(value: str) -> None:
        """Validate DNS hostname format."""
        if len(value) > 253:
            raise ValidationError(
                f"hostname must be 253 characters or less (got {len(value)})"
            )
        # DNS hostname pattern: labels separated by dots
        label_pattern = r"[a-z0-9]([a-z0-9-]*[a-z0-9])?"
        hostname_pattern = f"^{label_pattern}(\\.{label_pattern})*$"
        if not re.match(hostname_pattern, value.lower()):
            raise ValidationError(f"Invalid hostname format: {value}")

    @staticmethod
    def _validate_cidr(value: str) -> None:
        """Validate CIDR notation (basic check)."""
        parts = value.split("/")
        if len(parts) != 2:
            raise ValidationError(f"Invalid CIDR format: {value} (must be IP/prefix)")
        ip, prefix = parts
        # Validate IP (simple check)
        ip_parts = ip.split(".")
        if len(ip_parts) != 4 or not all(
            p.isdigit() and 0 <= int(p) <= 255 for p in ip_parts
        ):
            raise ValidationError(f"Invalid IP address in CIDR: {ip}")
        # Validate prefix
        if not prefix.isdigit() or not 0 <= int(prefix) <= 32:
            raise ValidationError(f"Invalid CIDR prefix: {prefix} (must be 0-32)")

    @staticmethod
    def _validate_label(value: str) -> None:
        """Validate Kubernetes label value."""
        if len(value) > 63:
            raise ValidationError(
                f"label must be 63 characters or less (got {len(value)})"
            )
        if value and not re.match(r"^[a-z0-9A-Z]([-a-z0-9A-Z_.]*[a-z0-9A-Z])?$", value):
            raise ValidationError(f"Invalid label format: {value}")

    additional: Dict[str, str] = field(default_factory=dict)


class Scenario(ABC):
    """Abstract base class for all chall-manager scenarios."""

    def __init__(self, config: ScenarioConfig):
        self.config = config

    @abstractmethod
    def generate_pulumi_code(self) -> str:
        """Generate Pulumi Python code for this scenario."""
        pass

    @abstractmethod
    def validate(self) -> None:
        """Validate the scenario configuration."""
        pass

    def to_file(self, filepath: str) -> None:
        """
        Write the generated Pulumi code to a file.

        Args:
            filepath: Path to write the file (must not contain path traversal)

        Raises:
            ValidationError: If filepath contains path traversal or is invalid
            IOError: If file cannot be written
        """
        # Validate filepath
        self._validate_filepath(filepath)

        # Generate code
        code = self.generate_pulumi_code()

        # Write with error handling
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)
        except (IOError, OSError, PermissionError) as e:
            raise ValidationError(f"Failed to write file {filepath}: {e}")

    @staticmethod
    def _validate_filepath(filepath: str) -> None:
        """
        Validate that filepath is safe and doesn't contain path traversal.

        Args:
            filepath: Path to validate

        Raises:
            ValidationError: If filepath is invalid or contains path traversal
        """
        if not filepath:
            raise ValidationError("filepath cannot be empty")

        # Resolve to absolute path to detect traversal
        abs_path = os.path.abspath(filepath)
        cwd = os.getcwd()

        # Check for path traversal (trying to write outside current directory tree)
        if not abs_path.startswith(os.path.abspath(cwd)):
            raise ValidationError(
                f"Path traversal detected: {filepath} resolves outside working directory"
            )

        # Check for suspicious patterns
        if ".." in filepath or filepath.startswith("/"):
            raise ValidationError(
                f"Invalid filepath: {filepath} (contains '..' or starts with '/')"
            )

        # Check filename is reasonable
        filename = os.path.basename(filepath)
        if not filename or filename.startswith("."):
            raise ValidationError(f"Invalid filename: {filename}")

        # Check file extension
        if not filename.endswith(".py"):
            raise ValidationError(f"Filepath must end with .py (got: {filepath})")

    def _generate_common_imports(self) -> str:
        """Generate common import statements."""
        return """import pulumi
from pulumi import Config, ResourceOptions
import pulumi_kubernetes as k8s"""

    def _generate_sdk_imports(self) -> str:
        """Generate chall-manager SDK imports."""
        return """
# Chall-manager SDK imports (these would be actual Python bindings)
# For now, we generate code that uses the Pulumi Kubernetes provider directly"""

    def _generate_config_loading(self) -> str:
        """Generate configuration loading code."""
        return f'''
# Load configuration from chall-manager
config = Config()
identity = config.get("identity") or "{self.config.identity}"
challenge_id = config.get("challenge_id") or "{self.config.challenge_id}"
'''

    def _generate_labels(self) -> str:
        """Generate standard labels."""
        labels = {
            "app.kubernetes.io/name": "identity",
            "app.kubernetes.io/component": "chall-manager",
            "app.kubernetes.io/part-of": "chall-manager",
            "chall-manager.ctfer.io/identity": "identity",
        }
        if self.config.label:
            labels["chall-manager.ctfer.io/label"] = self.config.label

        return f"""labels = {{
    "app.kubernetes.io/name": identity,
    "app.kubernetes.io/component": "chall-manager",
    "app.kubernetes.io/part-of": "chall-manager",
    "chall-manager.ctfer.io/identity": identity,{f'\n    "chall-manager.ctfer.io/label": "{self.config.label}",' if self.config.label else ""}
}}"""

    def _generate_image_pull_secrets(self) -> str:
        """Generate image pull secrets configuration."""
        if not self.config.image_pull_secrets:
            return ""

        secrets_str = ", ".join(
            [f'{{"name": "{s}"}}' for s in self.config.image_pull_secrets]
        )
        return f"""
# Image pull secrets for private registries
image_pull_secrets = [{secrets_str}]
"""

    def _generate_packet_capture_config(self, container_name: str) -> str:
        """Generate packet capture sidecar configuration if enabled."""
        if not self.config.packet_capture_pvc:
            return ""

        return f'''
# Packet capture sidecar configuration
packet_capture_enabled = True
pcap_pvc_name = "{self.config.packet_capture_pvc}"

# Packet capture sidecar container
pcap_sidecar = {{
    "name": f"{{identity}}-pcap",
    "image": "nicolaka/netshoot:v0.13",
    "imagePullPolicy": "IfNotPresent",
    "command": ["/bin/bash", "/scripts/capture-daemon.sh"],
    "env": [
        {{"name": "CONTAINER_NAME", "value": "{container_name}"}},
        {{"name": "IDENTITY", "value": identity}},
        {{"name": "LABEL", "value": "{self.config.label or ""}"}},
        {{"name": "CAPTURE_DIR", "value": "/captures"}},
    ],
    "securityContext": {{
        "privileged": True,
        "runAsUser": 0,
        "capabilities": {{"add": ["NET_RAW", "NET_ADMIN"]}},
    }},
    "volumeMounts": [
        {{"name": "packet-captures", "mountPath": "/captures", "subPath": f"captures/{{challenge_id}}/{{identity}}/{container_name}"}},
        {{"name": "capture-script", "mountPath": "/scripts", "readOnly": True}},
    ],
    "resources": {{
        "limits": {{"cpu": "200m", "memory": "256Mi"}},
        "requests": {{"cpu": "100m", "memory": "128Mi"}},
    }},
}}'''

    def _generate_namespace(self) -> str:
        """Generate namespace resource.

        This method is used by all scenario generators (monopod, multipod, kompose)
        to create a Kubernetes namespace with proper security labels.
        """
        return """
# Create namespace
ns = k8s.core.v1.Namespace(
    "ns",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name=identity,
        labels={
            "pod-security.kubernetes.io/enforce": "baseline",
            "pod-security.kubernetes.io/enforce-version": "latest",
        },
    ),
)
"""

    def _generate_files_configmap(self, container, var_prefix: str = "") -> str:
        """Generate ConfigMap for container files.

        This method is used by monopod and multipod scenario generators.

        Args:
            container: Container object with files to mount
            var_prefix: Optional prefix for the variable name (e.g., container name)
        """
        files_dict = repr(container.files)
        var_name = f"{var_prefix}_files_configmap" if var_prefix else "files_configmap"
        comment = (
            f"# ConfigMap for {container.name} files"
            if var_prefix
            else "# ConfigMap for container files"
        )

        return f'''
{comment}
{var_name} = k8s.core.v1.ConfigMap(
    "{container.name}-files",
    metadata=k8s.meta.v1.ObjectMetaArgs(
        name="{container.name}-files",
        namespace=ns.metadata.name,
    ),
    data={files_dict},
    opts=ResourceOptions(depends_on=[ns]),
)
'''

    def _generate_footer(self) -> str:
        """Generate the footer code."""
        return """
# Export connection info
pulumi.export("connection_info", connection_info)
"""


class ValidationError(Exception):
    """Raised when scenario validation fails."""

    pass

"""Container and networking configuration classes."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
import re


class ExposeType(Enum):
    """Types of service exposure."""

    INTERNAL = "internal"
    NODE_PORT = "NodePort"
    LOAD_BALANCER = "LoadBalancer"
    INGRESS = "ingress"


@dataclass
class PortBinding:
    """Port binding configuration."""

    port: int
    protocol: str = "TCP"
    expose_type: ExposeType = ExposeType.INTERNAL
    annotations: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        """Validate port binding after initialization."""
        # Normalize protocol to uppercase
        self.protocol = self.protocol.upper()

        if self.protocol not in ("TCP", "UDP"):
            raise ValueError(f"Invalid protocol: {self.protocol} (must be TCP or UDP)")

        if self.port < 1 or self.port > 65535:
            raise ValueError(f"Invalid port number: {self.port} (must be 1-65535)")

        # Warn about privileged ports (informational)
        if self.port < 1024:
            # Note: Just validate range, don't warn as it might be intentional
            pass


@dataclass
class Container:
    """Container configuration."""

    name: str
    image: str
    ports: List[PortBinding] = field(default_factory=list)
    envs: Dict[str, str] = field(default_factory=dict)
    files: Dict[str, str] = field(default_factory=dict)
    limit_cpu: Optional[str] = None
    limit_memory: Optional[str] = None
    packet_capture: bool = False

    # Kubernetes ConfigMap size limit
    MAX_CONFIGMAP_SIZE = 1024 * 1024  # 1MB
    MAX_FILE_COUNT = 100
    MAX_ENV_COUNT = 100

    def __post_init__(self):
        """Validate container configuration after initialization."""
        self._validate_name()
        self._validate_image()
        self._validate_envs()
        self._validate_files()
        self._validate_resources()

    def _validate_name(self) -> None:
        """Validate container name follows Kubernetes DNS-1123 label."""
        if not self.name:
            raise ValueError("Container name is required")
        if len(self.name) > 63:
            raise ValueError(
                f"Container name must be 63 characters or less (got {len(self.name)})"
            )
        if not re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", self.name):
            raise ValueError(
                f"Container name must consist of lowercase alphanumeric characters or '-', "
                f"and start and end with an alphanumeric character (got: {self.name})"
            )

    def _validate_image(self) -> None:
        """Validate container image reference."""
        if not self.image:
            raise ValueError("Container image is required")
        # Basic image format validation (registry/repo:tag or repo:tag)
        if len(self.image) > 256:
            raise ValueError(f"Image reference too long: {len(self.image)} (max 256)")

    def _validate_envs(self) -> None:
        """Validate environment variables."""
        if len(self.envs) > self.MAX_ENV_COUNT:
            raise ValueError(
                f"Too many environment variables: {len(self.envs)} (max {self.MAX_ENV_COUNT})"
            )

        for key, value in self.envs.items():
            # Validate env var name
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
                raise ValueError(f"Invalid environment variable name: {key}")
            # Validate env var value (check for control characters, excessive length)
            if len(value) > 32768:  # 32KB limit per value
                raise ValueError(
                    f"Environment variable {key} value too long: {len(value)} bytes"
                )
            if "\x00" in value:
                raise ValueError(f"Environment variable {key} contains null byte")

    def _validate_files(self) -> None:
        """Validate files for ConfigMap."""
        if len(self.files) > self.MAX_FILE_COUNT:
            raise ValueError(
                f"Too many files: {len(self.files)} (max {self.MAX_FILE_COUNT})"
            )

        total_size = 0
        for path, content in self.files.items():
            # Validate file path
            if not path.startswith("/"):
                raise ValueError(f"File path must be absolute: {path}")
            if ".." in path:
                raise ValueError(f"File path contains '..': {path}")
            if len(path) > 256:
                raise ValueError(f"File path too long: {len(path)} (max 256)")

            # Validate content size
            content_bytes = len(content.encode("utf-8"))
            total_size += content_bytes
            if content_bytes > 524288:  # 512KB per file
                raise ValueError(
                    f"File {path} too large: {content_bytes} bytes (max 512KB)"
                )

        if total_size > self.MAX_CONFIGMAP_SIZE:
            raise ValueError(
                f"Total file size {total_size} bytes exceeds ConfigMap limit {self.MAX_CONFIGMAP_SIZE} bytes"
            )

    def _validate_resources(self) -> None:
        """Validate resource limits."""
        if self.limit_cpu:
            # Validate Kubernetes CPU format: number or number with 'm' suffix
            if not re.match(r"^\d+m?$", self.limit_cpu):
                raise ValueError(
                    f"Invalid CPU limit format: {self.limit_cpu} (use '100m' or '1')"
                )

        if self.limit_memory:
            # Validate Kubernetes memory format: number with unit (Ki, Mi, Gi, etc.)
            if not re.match(
                r"^\d+(Ki|Mi|Gi|Ti|Pi|Ei|k|M|G|T|P|E)?$", self.limit_memory
            ):
                raise ValueError(
                    f"Invalid memory limit format: {self.limit_memory} (use '512Mi', '1Gi', etc.)"
                )

    def validate(self) -> None:
        """Validate container configuration."""
        if not self.image:
            raise ValueError("Container image is required")
        if not self.name:
            raise ValueError("Container name is required")
        if not self.ports:
            raise ValueError(f"Container {self.name} must have at least one port")

        for port in self.ports:
            if port.port < 1 or port.port > 65535:
                raise ValueError(f"Invalid port number: {port.port}")

    def to_kubernetes_container(self, identity: str) -> dict:
        """Convert container configuration to Kubernetes container spec.

        Generates a Kubernetes-compatible container specification dictionary
        that includes ports, environment variables, file mounts, and resource
        limits.

        Args:
            identity: The instance identity for labeling purposes

        Returns:
            dict: Kubernetes container specification with the following structure:
                - name: Container name
                - image: Container image reference
                - ports: List of container ports
                - env: Environment variables (if any)
                - volumeMounts: Volume mount points for files (if any)
                - resources: CPU and memory limits (if specified)
        """
        container = {
            "name": self.name,
            "image": self.image,
            "ports": [
                {
                    "containerPort": p.port,
                    "protocol": p.protocol,
                }
                for p in self.ports
            ],
        }

        if self.envs:
            container["env"] = [{"name": k, "value": v} for k, v in self.envs.items()]

        if self.files:
            # Files are mounted via ConfigMap
            container["volumeMounts"] = [
                {
                    "name": f"{self.name}-files",
                    "mountPath": path,
                    "subPath": path.lstrip("/").replace("/", "-"),
                }
                for path in self.files.keys()
            ]

        resources = {}
        if self.limit_cpu:
            resources["cpu"] = self.limit_cpu
        if self.limit_memory:
            resources["memory"] = self.limit_memory

        if resources:
            container["resources"] = {"limits": resources}

        return container

    def get_port_list(self) -> str:
        """Get comma-separated list of ports for packet capture."""
        return ",".join([f"{p.port}:{p.protocol.lower()}" for p in self.ports])


@dataclass
class Rule:
    """Network rule for multi-pod setups."""

    from_container: str
    to_container: str
    ports: List[int] = field(default_factory=list)
    protocol: str = "TCP"

    def validate(self) -> None:
        """Validate network rule configuration.

        Ensures that:
        - Both from_container and to_container are specified
        - Protocol is either TCP or UDP

        Raises:
            ValueError: If validation fails
        """
        if not self.from_container or not self.to_container:
            raise ValueError("Both from_container and to_container are required")
        if self.protocol not in ("TCP", "UDP"):
            raise ValueError(f"Invalid protocol: {self.protocol}")

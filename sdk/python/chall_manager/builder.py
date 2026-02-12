"""Builder pattern for creating scenarios easily."""

from typing import Dict, List, Optional, Union
from dataclasses import dataclass, field

from .base import Scenario, ScenarioConfig
from .containers import Container, PortBinding, Rule, ExposeType
from .monopod import MonopodScenario, MonopodConfig
from .multipod import MultipodScenario, MultipodConfig
from .kompose import KomposeScenario, KomposeConfig


class ScenarioBuilder:
    """
    Fluent builder for creating chall-manager scenarios.

    Example:
        # Monopod scenario
        scenario = (ScenarioBuilder()
            .with_identity("web-challenge")
            .with_hostname("ctf.example.com")
            .with_container(
                Container(
                    name="web",
                    image="nginx:latest",
                    ports=[PortBinding(80, expose_type=ExposeType.INGRESS)],
                )
            )
            .with_image_pull_secrets(["gitlab-registry"])
            .build_monopod())

        # Multipod scenario
        scenario = (ScenarioBuilder()
            .with_identity("multi-service")
            .with_container("web", Container(...))
            .with_container("api", Container(...))
            .with_rule("web", "api", ports=[8080])
            .build_multipod())

        # Kompose scenario
        scenario = (ScenarioBuilder()
            .with_identity("compose-app")
            .with_docker_compose(yaml_content)
            .with_packet_capture({"web": True})
            .build_kompose())
    """

    def __init__(self):
        self._identity: str = ""
        self._challenge_id: str = ""
        self._hostname: str = ""
        self._label: Optional[str] = None
        self._from_cidr: str = "0.0.0.0/0"
        self._ingress_namespace: str = ""
        self._ingress_labels: Dict[str, str] = {}
        self._ingress_annotations: Dict[str, str] = {}
        self._image_pull_secrets: List[str] = []
        self._packet_capture_pvc: Optional[str] = None
        self._additional: Dict[str, str] = {}

        # Monopod specific
        self._container: Optional[Container] = None

        # Multipod specific
        self._containers: Dict[str, Container] = {}
        self._rules: List[Rule] = []

        # Kompose specific
        self._yaml_content: str = ""
        self._ports: Dict[str, List[PortBinding]] = {}
        self._packet_capture: Dict[str, bool] = {}

    # Common configuration

    def with_identity(self, identity: str) -> "ScenarioBuilder":
        """Set the identity for this scenario."""
        self._identity = identity
        return self

    def with_challenge_id(self, challenge_id: str) -> "ScenarioBuilder":
        """Set the challenge ID."""
        self._challenge_id = challenge_id
        return self

    def with_hostname(self, hostname: str) -> "ScenarioBuilder":
        """Set the hostname for ingress."""
        self._hostname = hostname
        return self

    def with_label(self, label: str) -> "ScenarioBuilder":
        """Set a label for this scenario."""
        self._label = label
        return self

    def with_from_cidr(self, cidr: str) -> "ScenarioBuilder":
        """Set the CIDR for network policies."""
        self._from_cidr = cidr
        return self

    def with_ingress_namespace(self, namespace: str) -> "ScenarioBuilder":
        """Set the ingress namespace."""
        self._ingress_namespace = namespace
        return self

    def with_ingress_labels(self, labels: Dict[str, str]) -> "ScenarioBuilder":
        """Set ingress labels."""
        self._ingress_labels = labels
        return self

    def with_ingress_annotations(
        self, annotations: Dict[str, str]
    ) -> "ScenarioBuilder":
        """Set ingress annotations."""
        self._ingress_annotations = annotations
        return self

    def with_image_pull_secrets(self, secrets: List[str]) -> "ScenarioBuilder":
        """Set image pull secrets for private registries."""
        self._image_pull_secrets = secrets
        return self

    def with_image_pull_secret(self, secret: str) -> "ScenarioBuilder":
        """Add a single image pull secret."""
        self._image_pull_secrets.append(secret)
        return self

    def with_packet_capture_pvc(self, pvc: str) -> "ScenarioBuilder":
        """Set the packet capture PVC name."""
        self._packet_capture_pvc = pvc
        return self

    def with_additional(self, key: str, value: str) -> "ScenarioBuilder":
        """Add an additional configuration key-value pair."""
        self._additional[key] = value
        return self

    # Monopod specific

    def with_container(self, container: Container) -> "ScenarioBuilder":
        """Set the container for a Monopod scenario."""
        self._container = container
        return self

    # Multipod specific

    def with_container_named(
        self, name: str, container: Container
    ) -> "ScenarioBuilder":
        """Add a named container for a Multipod scenario."""
        self._containers[name] = container
        return self

    def with_rule(
        self,
        from_container: str,
        to_container: str,
        ports: Optional[List[int]] = None,
        protocol: str = "TCP",
    ) -> "ScenarioBuilder":
        """Add a network rule between containers."""
        self._rules.append(
            Rule(
                from_container=from_container,
                to_container=to_container,
                ports=ports or [],
                protocol=protocol,
            )
        )
        return self

    # Kompose specific

    def with_docker_compose(self, yaml_content: str) -> "ScenarioBuilder":
        """Set the Docker Compose YAML content."""
        self._yaml_content = yaml_content
        return self

    def with_service_ports(
        self, service_name: str, ports: List[PortBinding]
    ) -> "ScenarioBuilder":
        """Set port bindings for a service in Kompose."""
        self._ports[service_name] = ports
        return self

    def with_packet_capture_for(
        self, service_name: str, enabled: bool = True
    ) -> "ScenarioBuilder":
        """Enable or disable packet capture for a service."""
        self._packet_capture[service_name] = enabled
        return self

    # Build methods

    def _build_base_config(self) -> ScenarioConfig:
        """Build the base configuration."""
        return ScenarioConfig(
            identity=self._identity,
            challenge_id=self._challenge_id or self._identity,
            hostname=self._hostname,
            label=self._label,
            from_cidr=self._from_cidr,
            ingress_namespace=self._ingress_namespace,
            ingress_labels=self._ingress_labels,
            ingress_annotations=self._ingress_annotations,
            image_pull_secrets=self._image_pull_secrets,
            packet_capture_pvc=self._packet_capture_pvc,
            additional=self._additional,
        )

    def build_monopod(self) -> MonopodScenario:
        """Build a single-container (monopod) scenario.

        Creates a scenario with a single container deployed as a Kubernetes Pod.
        Suitable for simple CTF challenges that don't require multiple services
        or complex networking.

        Returns:
            MonopodScenario: A validated monopod scenario ready to generate code

        Raises:
            ValueError: If container configuration is invalid or missing
        """
        base_config = self._build_base_config()
        config = MonopodConfig(
            **base_config.__dict__,
            container=self._container,
        )
        scenario = MonopodScenario(config)
        scenario.validate()
        return scenario

    def build_multipod(self) -> MultipodScenario:
        """Build a multi-container (multipod) scenario.

        Creates a scenario with multiple containers deployed as separate Pods
        with network policies controlling traffic between them. Suitable for
        complex CTF challenges requiring multiple services with specific
        network isolation rules.

        Returns:
            MultipodScenario: A validated multipod scenario ready to generate code

        Raises:
            ValueError: If container or rule configuration is invalid
        """
        base_config = self._build_base_config()
        config = MultipodConfig(
            **base_config.__dict__,
            containers=self._containers,
            rules=self._rules,
        )
        scenario = MultipodScenario(config)
        scenario.validate()
        return scenario

    def build_kompose(self) -> KomposeScenario:
        """Build a Kompose scenario from Docker Compose YAML.

        Creates a scenario by converting Docker Compose YAML into Kubernetes
        resources. Suitable for migrating existing Docker Compose-based CTF
        challenges to Kubernetes.

        Returns:
            KomposeScenario: A validated kompose scenario ready to generate code

        Raises:
            ValueError: If YAML content is invalid or missing
        """
        base_config = self._build_base_config()
        config = KomposeConfig(
            **base_config.__dict__,
            yaml_content=self._yaml_content,
            ports=self._ports,
            packet_capture=self._packet_capture,
        )
        scenario = KomposeScenario(config)
        scenario.validate()
        return scenario

    def build(self, scenario_type: str) -> Scenario:
        """
        Build a scenario of the specified type.

        Args:
            scenario_type: One of 'monopod', 'multipod', or 'kompose'

        Returns:
            The built scenario
        """
        builders = {
            "monopod": self.build_monopod,
            "multipod": self.build_multipod,
            "kompose": self.build_kompose,
        }

        if scenario_type not in builders:
            raise ValueError(
                f"Unknown scenario type: {scenario_type}. Choose from: {list(builders.keys())}"
            )

        return builders[scenario_type]()


def quick_monopod(
    identity: str,
    image: str,
    port: int,
    hostname: str = "",
    expose_type: ExposeType = ExposeType.INTERNAL,
    **kwargs,
) -> MonopodScenario:
    """
    Quickly create a Monopod scenario.

    Args:
        identity: The scenario identity
        image: Container image
        port: Port number
        hostname: Optional hostname for ingress
        expose_type: How to expose the port
        **kwargs: Additional builder options

    Returns:
        A configured MonopodScenario
    """
    builder = ScenarioBuilder().with_identity(identity)

    if hostname:
        builder = builder.with_hostname(hostname)

    for key, value in kwargs.items():
        if hasattr(builder, f"with_{key}"):
            getattr(builder, f"with_{key}")(value)

    container = Container(
        name="main",
        image=image,
        ports=[PortBinding(port, expose_type=expose_type)],
    )

    return builder.with_container(container).build_monopod()


def quick_multipod(
    identity: str, containers: Dict[str, Container], hostname: str = "", **kwargs
) -> MultipodScenario:
    """
    Quickly create a Multipod scenario.

    Args:
        identity: The scenario identity
        containers: Dictionary of container name -> Container
        hostname: Optional hostname for ingress
        **kwargs: Additional builder options

    Returns:
        A configured MultipodScenario
    """
    builder = ScenarioBuilder().with_identity(identity)

    if hostname:
        builder = builder.with_hostname(hostname)

    for key, value in kwargs.items():
        if hasattr(builder, f"with_{key}"):
            getattr(builder, f"with_{key}")(value)

    for name, container in containers.items():
        builder = builder.with_container_named(name, container)

    return builder.build_multipod()


def quick_kompose(identity: str, yaml_content: str, **kwargs) -> KomposeScenario:
    """
    Quickly create a Kompose scenario.

    Args:
        identity: The scenario identity
        yaml_content: Docker Compose YAML content
        **kwargs: Additional builder options

    Returns:
        A configured KomposeScenario
    """
    builder = ScenarioBuilder().with_identity(identity)

    for key, value in kwargs.items():
        if hasattr(builder, f"with_{key}"):
            getattr(builder, f"with_{key}")(value)

    return builder.with_docker_compose(yaml_content).build_kompose()

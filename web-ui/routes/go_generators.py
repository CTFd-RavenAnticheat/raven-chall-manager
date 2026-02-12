"""Go scenario code generators for chall-manager."""

import re
import os
from typing import Dict, List, Optional, Any


def generate_go_mod(challenge_id: str) -> str:
    """Generate go.mod file for the scenario by reading from template.

    Args:
        challenge_id: The challenge identifier

    Returns:
        go.mod file content
    """
    # Ensure challenge_id is not empty and is valid as a Go module name
    if not challenge_id or not challenge_id.strip():
        challenge_id = "scenario"

    # Sanitize challenge_id for Go module path (lowercase alphanumeric and hyphens)
    challenge_id = re.sub(r"[^a-zA-Z0-9_-]", "-", challenge_id.strip())
    if not challenge_id:
        challenge_id = "scenario"

    # Read the template go.mod file
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "templates",
        "go",
        "go.mod.template",
    )

    with open(template_path, "r") as f:
        go_mod_content = f.read()

    # Replace the module name (first line)
    # Original: module github.com/CTFd-RavenAnticheat/raven-chall-manager/examples/custom-packet-tests/evenbtrfs
    # Replace with: module {challenge_id}
    lines = go_mod_content.split("\n")
    lines[0] = f"module {challenge_id}"

    return "\n".join(lines)


def generate_pulumi_yaml(project_name: str, stack_name: str = "dev") -> str:
    """Generate Pulumi.yaml file for the scenario.

    Args:
        project_name: Project name for Pulumi
        stack_name: Stack name (default: "dev")

    Returns:
        Pulumi.yaml file content
    """
    return f"""name: {project_name}
runtime: go
description: A Pulumi program for {project_name}
"""


def generate_port_bindings(ports: List[Dict[str, Any]]) -> str:
    """Generate Go code for port bindings array value only (without field name).

    Args:
        ports: List of port configurations

    Returns:
        Go code string for port bindings array (just the value, not "Ports:")
    """
    if not ports:
        return "k8s.PortBindingArray{}"

    port_lines = ["k8s.PortBindingArray{"]
    for port_config in ports:
        port_num = port_config.get("port", 80)
        protocol = port_config.get("protocol", "TCP")
        expose_type = port_config.get("expose_type", "internal")

        expose_map = {
            "internal": "k8s.ExposeInternal",
            "nodeport": "k8s.ExposeNodePort",
            "loadbalancer": "k8s.ExposeLoadBalancer",
            "ingress": "k8s.ExposeIngress",
        }
        expose_go = expose_map.get(expose_type.lower(), "k8s.ExposeInternal")

        port_lines.append("\t\t\t\t\tk8s.PortBindingArgs{")
        port_lines.append(f"\t\t\t\t\t\tPort:       pulumi.Int({port_num}),")
        # Only include Protocol if it's not TCP (the default)
        if protocol.upper() != "TCP":
            port_lines.append(f'\t\t\t\t\t\tProtocol:   pulumi.String("{protocol}"),')
        port_lines.append(f"\t\t\t\t\t\tExposeType: {expose_go},")
        port_lines.append("\t\t\t\t\t},")
    port_lines.append("\t\t\t\t}")
    return "\n".join(port_lines)


def generate_env_vars(envs: Dict[str, str]) -> str:
    """Generate Go code for environment variables.

    Args:
        envs: Dictionary of environment variables

    Returns:
        Go code string for environment variables
    """
    if not envs:
        return ""

    env_lines = ["\t\t\t\tEnvs: pulumi.StringMap{"]
    for key, value in envs.items():
        env_lines.append(f'\t\t\t\t\t"{key}": pulumi.String("{value}"),')
    env_lines.append("\t\t\t\t},")
    return "\n".join(env_lines)


def generate_files(files: Dict[str, str]) -> str:
    """Generate Go code for file mounts.

    Args:
        files: Dictionary mapping file paths to contents

    Returns:
        Go code string for file mounts
    """
    if not files:
        return ""

    file_lines = ["\t\t\t\tFiles: pulumi.StringMap{"]
    for path, content in files.items():
        # Escape special characters in content
        escaped_content = (
            content.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        )
        file_lines.append(f'\t\t\t\t\t"{path}": pulumi.String("{escaped_content}"),')
    file_lines.append("\t\t\t\t},")
    return "\n".join(file_lines)


def generate_exposed_monopod(
    scenario_name: str,
    hostname: str,
    image: str,
    ports: List[Dict[str, Any]],
    envs: Optional[Dict[str, str]] = None,
    files: Optional[Dict[str, str]] = None,
    limit_cpu: str = "500m",
    limit_memory: str = "256Mi",
    packet_capture: bool = True,
    packet_capture_pvc: str = "pcap-core",
    connection_format: str = "nc %s",
    ingress_namespace: str = "networking",
    ingress_labels: Optional[Dict[str, str]] = None,
    ingress_annotations: Optional[Dict[str, str]] = None,
    image_pull_secrets: Optional[List[str]] = None,
) -> str:
    """Generate Go code for ExposedMonopod scenario.

    Args:
        scenario_name: Scenario/challenge name (used as resource name)
        hostname: Hostname for ingress
        image: Container image to use
        ports: List of port configurations
        envs: Environment variables (optional)
        files: Files to mount (optional)
        limit_cpu: CPU limit (default: "500m")
        limit_memory: Memory limit (default: "256Mi")
        packet_capture: Enable packet capture (default: True)
        packet_capture_pvc: PVC name for packet capture (default: "pcap-core")
        connection_format: Format string for connection info (default: "nc %s")
        ingress_namespace: Namespace for ingress controller
        ingress_labels: Labels for ingress (optional)
        ingress_annotations: Annotations for ingress (optional)
        image_pull_secrets: List of image pull secret names (optional)

    Returns:
        Complete main.go content
    """
    envs = envs or {}
    files = files or {}
    ingress_labels = ingress_labels or {"app": "traefik"}
    ingress_annotations = ingress_annotations or {}

    # WORKAROUND: SDK bug - if no files, vs variable is nil causing panic
    # Always include at least one file to ensure container.HasFiles() returns true
    if not files:
        files = {
            "/tmp/.chall-manager-keep": "# This file prevents an SDK bug with empty file lists"
        }

    # Generate code sections
    port_bindings = generate_port_bindings(ports)
    env_vars = generate_env_vars(envs)
    file_mounts = generate_files(files)

    # Build ingress labels
    ingress_labels_lines = ["map[string]string{"]
    for key, value in ingress_labels.items():
        ingress_labels_lines.append(f'\t\t\t\t"{key}": "{value}",')
    ingress_labels_lines.append("\t\t\t}")
    ingress_labels_str = "\n\t\t\t".join(ingress_labels_lines)

    # Build ingress annotations
    ingress_annotations_lines = ["map[string]string{"]
    for key, value in ingress_annotations.items():
        ingress_annotations_lines.append(f'\t\t\t\t"{key}": "{value}",')
    ingress_annotations_lines.append("\t\t\t}")
    ingress_annotations_str = "\n\t\t\t".join(ingress_annotations_lines)

    # Build ingress annotations line
    ingress_annotations_line = ""
    if ingress_annotations:
        ingress_annotations_line = (
            f"\t\t\tIngressAnnotations: pulumi.ToStringMap({ingress_annotations_str}),"
        )

    # Build image pull secrets array
    image_pull_secrets_line = ""
    if image_pull_secrets:
        secrets_list = ", ".join([f'pulumi.String("{s}")' for s in image_pull_secrets])
        image_pull_secrets_line = (
            f"\t\t\tImagePullSecrets: pulumi.StringArray{{{secrets_list}}},"
        )

    # Get first port for connection info
    first_port = ports[0]["port"] if ports else 80
    first_protocol = ports[0].get("protocol", "TCP") if ports else "TCP"

    code = f"""package main

import (
\t"github.com/CTFd-RavenAnticheat/raven-chall-manager/sdk"
\tk8s "github.com/CTFd-RavenAnticheat/raven-chall-manager/sdk/kubernetes"
\t"github.com/pulumi/pulumi/sdk/v3/go/pulumi"
)

func main() {{
\tsdk.Run(func(req *sdk.Request, resp *sdk.Response, opts ...pulumi.ResourceOption) error {{
\t\t// Create the ExposedMonopod resource
\t\tcm, err := k8s.NewExposedMonopod(req.Ctx, "{scenario_name}", &k8s.ExposedMonopodArgs{{
\t\t\tChallengeID:      pulumi.String(req.Config.ChallengeID),
\t\t\tPacketCapturePVC: pulumi.StringPtr("{packet_capture_pvc}"),
\t\t\tIdentity:         pulumi.String(req.Config.Identity),
\t\t\tHostname:         pulumi.String("{hostname}"),
\t\t\tContainer: k8s.ContainerArgs{{
\t\t\t\tImage: pulumi.String("{image}"),
\t\t\t\tPorts: {port_bindings},
{env_vars}
{file_mounts}
\t\t\t\tPacketCapture: pulumi.BoolPtr({str(packet_capture).lower()}),
\t\t\t\tLimitCPU:    pulumi.StringPtr("{limit_cpu}"),
\t\t\t\tLimitMemory: pulumi.StringPtr("{limit_memory}"),
			}},
			IngressNamespace: pulumi.String("{ingress_namespace}"),
			IngressLabels: pulumi.ToStringMap({ingress_labels_str}),
{ingress_annotations_line}
{image_pull_secrets_line}
		}}, opts...)
\t\tif err != nil {{
\t\t\treturn err
\t\t}}

\t\tresp.ConnectionInfo = pulumi.Sprintf("{connection_format}",
\t\t\tcm.URLs.MapIndex(pulumi.String("{first_port}/{first_protocol}")))

\treturn nil
\t}})
}}
"""

    return code


def generate_exposed_multipod(
    scenario_name: str,
    hostname: str,
    containers: Dict[str, Dict[str, Any]],
    rules: List[Dict[str, Any]],
    packet_capture_pvc: str = "pcap-core",
    connection_format: str = "nc %s",
    ingress_namespace: str = "networking",
    ingress_labels: Optional[Dict[str, str]] = None,
    ingress_annotations: Optional[Dict[str, str]] = None,
    image_pull_secrets: Optional[List[str]] = None,
) -> str:
    """Generate Go code for ExposedMultipod scenario.

    Args:
        scenario_name: Scenario/challenge name (used as resource name)
        hostname: Hostname for ingress
        containers: Dictionary of container configurations
        rules: List of network rules
        packet_capture_pvc: PVC name for packet capture (default: "pcap-core")
        connection_format: Format string for connection info (default: "nc %s")
        ingress_namespace: Namespace for ingress controller
        ingress_labels: Labels for ingress (optional)
        ingress_annotations: Annotations for ingress (optional)
        image_pull_secrets: List of image pull secret names (optional)

    Returns:
        Complete main.go content
    """
    ingress_labels = ingress_labels or {"app": "traefik"}
    ingress_annotations = ingress_annotations or {}

    # Generate containers map
    container_lines = ["\t\t\tContainers: k8s.ContainerMap{"]
    for name, config in containers.items():
        container_lines.append(f'\t\t\t\t"{name}": k8s.ContainerArgs{{')
        container_lines.append(f'\t\t\t\t\tImage: pulumi.String("{config["image"]}"),')

        # Ports
        port_bindings = generate_port_bindings(config.get("ports", []))
        # Indent the port bindings properly
        port_lines = port_bindings.split("\n")
        for line in port_lines:
            container_lines.append("\t" + line)
        container_lines.append(",")

        # Envs
        if config.get("envs"):
            env_lines = generate_env_vars(config["envs"]).split("\n")
            for line in env_lines:
                container_lines.append("\t" + line)

        # Files - WORKAROUND: SDK bug requires at least one file
        files_config = config.get("files", {})
        if not files_config:
            files_config = {
                "/tmp/.chall-manager-keep": "# This file prevents an SDK bug with empty file lists"
            }
        file_lines = generate_files(files_config).split("\n")
        for line in file_lines:
            container_lines.append("\t" + line)

        # Resource limits (with defaults)
        limit_cpu = config.get("limit_cpu", "500m")
        limit_memory = config.get("limit_memory", "256Mi")
        container_lines.append(f'\t\t\t\t\tLimitCPU: pulumi.StringPtr("{limit_cpu}"),')
        container_lines.append(
            f'\t\t\t\t\tLimitMemory: pulumi.StringPtr("{limit_memory}"),'
        )

        # Packet capture (default: true)
        packet_capture = config.get("packet_capture", True)
        container_lines.append(
            f"\t\t\t\t\tPacketCapture: pulumi.BoolPtr({str(packet_capture).lower()}),"
        )

        container_lines.append("\t\t\t\t},")
    container_lines.append("\t\t\t},")
    containers_str = "\n".join(container_lines)

    # Generate rules array
    rules_lines = ["\t\t\tRules: k8s.RuleArray{"]
    for rule in rules:
        rules_lines.append("\t\t\t\tk8s.RuleArgs{")
        rules_lines.append(f'\t\t\t\t\tFrom: pulumi.String("{rule["from"]}"),')
        rules_lines.append(f'\t\t\t\t\tTo:   pulumi.String("{rule["to"]}"),')
        rules_lines.append(f"\t\t\t\t\tOn:   pulumi.Int({rule['port']}),")
        rules_lines.append("\t\t\t\t},")
    rules_lines.append("\t\t\t},")
    rules_str = "\n".join(rules_lines)

    # Build ingress labels
    ingress_labels_lines = ["map[string]string{"]
    for key, value in ingress_labels.items():
        ingress_labels_lines.append(f'\t\t\t\t"{key}": "{value}",')
    ingress_labels_lines.append("\t\t\t}")
    ingress_labels_str = "\n\t\t\t".join(ingress_labels_lines)

    # Build ingress annotations
    ingress_annotations_lines = ["map[string]string{"]
    for key, value in ingress_annotations.items():
        ingress_annotations_lines.append(f'\t\t\t\t"{key}": "{value}",')
    ingress_annotations_lines.append("\t\t\t}")
    ingress_annotations_str = "\n\t\t\t".join(ingress_annotations_lines)

    # Build packet capture PVC (always present)
    pvc_line = f'\t\t\tPacketCapturePVC: pulumi.StringPtr("{packet_capture_pvc}"),'

    # Build ingress annotations line
    ingress_annotations_line = ""
    if ingress_annotations:
        ingress_annotations_line = (
            f"\t\t\tIngressAnnotations: pulumi.ToStringMap({ingress_annotations_str}),"
        )

    # Build image pull secrets array
    image_pull_secrets_line = ""
    if image_pull_secrets:
        secrets_list = ", ".join([f'pulumi.String("{s}")' for s in image_pull_secrets])
        image_pull_secrets_line = (
            f"\t\t\tImagePullSecrets: pulumi.StringArray{{{secrets_list}}},"
        )

    # Find exposed container for connection info
    exposed_container = None
    exposed_port = None
    for name, config in containers.items():
        for port in config.get("ports", []):
            if port.get("expose_type", "").lower() in [
                "ingress",
                "nodeport",
                "loadbalancer",
            ]:
                exposed_container = name
                exposed_port = port["port"]
                break
        if exposed_container:
            break

    connection_info = ""
    if exposed_container and exposed_port:
        connection_info = f"""
\t\t// Export connection information
\t\tconnURL := cm.URLs.MapIndex(pulumi.String("{exposed_container}")).MapIndex(pulumi.String("{exposed_port}/TCP"))
\t\tresp.ConnectionInfo = pulumi.Sprintf("{connection_format}", connURL)
"""

    code = f"""package main

import (
\t"github.com/CTFd-RavenAnticheat/raven-chall-manager/sdk"
\tk8s "github.com/CTFd-RavenAnticheat/raven-chall-manager/sdk/kubernetes"
\t"github.com/pulumi/pulumi/sdk/v3/go/pulumi"
)

func main() {{
\tsdk.Run(func(req *sdk.Request, resp *sdk.Response, opts ...pulumi.ResourceOption) error {{
\t\t// Create the ExposedMultipod resource
\t\tcm, err := k8s.NewExposedMultipod(req.Ctx, "{scenario_name}", &k8s.ExposedMultipodArgs{{
\t\t\tChallengeID:      pulumi.String(req.Config.ChallengeID),
{pvc_line}
\t\t\tIdentity:         pulumi.String(req.Config.Identity),
\t\t\tHostname:         pulumi.String("{hostname}"),
{containers_str}
{rules_str}
			IngressNamespace: pulumi.String("{ingress_namespace}"),
			IngressLabels: pulumi.ToStringMap({ingress_labels_str}),
{ingress_annotations_line}
{image_pull_secrets_line}
		}}, opts...)
\t\tif err != nil {{
\t\t\treturn err
\t\t}}
{connection_info}
\t\treturn nil
\t}})
}}
"""

    return code


def generate_kompose(
    scenario_name: str,
    hostname: str,
    yaml_content: str,
    ports: Dict[str, List[Dict[str, Any]]],
    packet_capture_pvc: str = "pcap-core",
    connection_format: str = "nc %s",
    ingress_namespace: str = "networking",
    ingress_labels: Optional[Dict[str, str]] = None,
    ingress_annotations: Optional[Dict[str, str]] = None,
) -> tuple[str, str]:
    """Generate Go code for Kompose scenario.

    Args:
        scenario_name: Scenario/challenge name (used as resource name)
        hostname: Hostname for ingress
        yaml_content: Docker Compose YAML content
        ports: Dictionary mapping service names to port configurations
        packet_capture_pvc: PVC name for packet capture (default: "pcap-core")
        connection_format: Format string for connection info (default: "nc %s")
        ingress_namespace: Namespace for ingress controller
        ingress_labels: Labels for ingress (optional)
        ingress_annotations: Annotations for ingress (optional)

    Returns:
        Tuple of (main.go content, docker-compose.yaml content)
    """
    ingress_labels = ingress_labels or {"app": "traefik"}
    ingress_annotations = ingress_annotations or {}

    # Generate ports map
    ports_lines = ["\t\t\tPorts: k8s.PortBindingMapArray{"]
    for service_name, service_ports in ports.items():
        ports_lines.append(f'\t\t\t\t"{service_name}": {{')
        for port_config in service_ports:
            port_num = port_config.get("port", 80)
            expose_type = port_config.get("expose_type", "internal")

            expose_map = {
                "internal": "k8s.ExposeInternal",
                "nodeport": "k8s.ExposeNodePort",
                "loadbalancer": "k8s.ExposeLoadBalancer",
                "ingress": "k8s.ExposeIngress",
            }
            expose_go = expose_map.get(expose_type.lower(), "k8s.ExposeInternal")

            ports_lines.append("\t\t\t\t\tk8s.PortBindingArgs{")
            ports_lines.append(f"\t\t\t\t\t\tPort:       pulumi.Int({port_num}),")
            ports_lines.append(f"\t\t\t\t\t\tExposeType: {expose_go},")
            ports_lines.append("\t\t\t\t\t},")
        ports_lines.append("\t\t\t\t},")
    ports_lines.append("\t\t\t},")
    ports_str = "\n".join(ports_lines)

    # Build ingress labels
    ingress_labels_map = []
    for key, value in ingress_labels.items():
        ingress_labels_map.append(f'\t\t\t\t"{key}": "{value}",')
    ingress_labels_str = "\n".join(ingress_labels_map)

    # Build ingress annotations
    ingress_annotations_map = []
    for key, value in ingress_annotations.items():
        ingress_annotations_map.append(f'\t\t\t\t"{key}": "{value}",')
    ingress_annotations_str = "\n".join(ingress_annotations_map)

    # Build packet capture PVC (always present)
    pvc_line = f'\t\t\tPacketCapturePVC: pulumi.StringPtr("{packet_capture_pvc}"),'

    # Build ingress annotations line
    ingress_annotations_line = ""
    if ingress_annotations:
        ingress_annotations_line = f"""\t\t\tIngressAnnotations: pulumi.StringMap{{
{ingress_annotations_str}
\t\t\t}},"""

    # Find exposed service for connection info
    exposed_service = None
    exposed_port = None
    for service_name, service_ports in ports.items():
        for port in service_ports:
            if port.get("expose_type", "").lower() in [
                "ingress",
                "nodeport",
                "loadbalancer",
            ]:
                exposed_service = service_name
                exposed_port = port["port"]
                break
        if exposed_service:
            break

    connection_info = ""
    if exposed_service and exposed_port:
        connection_info = f"""
\t\t// Export connection information
\t\tconnURL := cm.URLs.MapIndex(pulumi.String("{exposed_service}")).MapIndex(pulumi.String("{exposed_port}/TCP"))
\t\tresp.ConnectionInfo = pulumi.Sprintf("{connection_format}", connURL)
"""

    main_go = f"""package main

import (
\t_ "embed"

\t"github.com/CTFd-RavenAnticheat/raven-chall-manager/sdk"
\tk8s "github.com/CTFd-RavenAnticheat/raven-chall-manager/sdk/kubernetes"
\t"github.com/pulumi/pulumi/sdk/v3/go/pulumi"
)

//go:embed docker-compose.yaml
var dc string

func main() {{
\tsdk.Run(func(req *sdk.Request, resp *sdk.Response, opts ...pulumi.ResourceOption) error {{
\t\t// Create the Kompose resource
\t\tcm, err := k8s.NewKompose(req.Ctx, "{scenario_name}", &k8s.KomposeArgs{{
\t\t\tChallengeID:      pulumi.String(req.Config.ChallengeID),
{pvc_line}
\t\t\tIdentity:         pulumi.String(req.Config.Identity),
\t\t\tHostname:         pulumi.String("{hostname}"),
\t\t\tYAML:             pulumi.String(dc),
{ports_str}
\t\t\tIngressNamespace: pulumi.String("{ingress_namespace}"),
\t\t\tIngressLabels: pulumi.StringMap{{
{ingress_labels_str}
\t\t\t}},
{ingress_annotations_line}
\t\t}}, opts...)
\t\tif err != nil {{
\t\t\treturn err
\t\t}}
{connection_info}
\t\treturn nil
\t}})
}}
"""

    return main_go, yaml_content

"""
Utility functions for the web UI - Go scenario generation.
"""

import io
import zipfile
import os
import re
import yaml
from routes.go_generators import (
    generate_exposed_monopod,
    generate_exposed_multipod,
    generate_kompose,
    generate_go_mod,
    generate_pulumi_yaml,
)


def build_monopod_scenario(data):
    """Build Monopod scenario using Go generator.

    Returns a dict with:
        - main_go: main.go content
        - go_mod: go.mod content
        - pulumi_yaml: Pulumi.yaml content
    """
    # Extract configuration
    scenario_name = data.get("identity", "scenario")
    hostname = data.get("hostname", "example.com")
    packet_capture_pvc = data.get("packet_capture_pvc", "pcap-core")
    ingress_namespace = data.get("ingress_namespace", "networking")
    connection_format = data.get("connection_format", "nc %s")

    # Ingress labels
    ingress_labels = {"app": "traefik"}
    if data.get("ingress_labels"):
        try:
            # Parse ingress labels if provided as key=value format
            for line in data["ingress_labels"].split("\n"):
                if "=" in line:
                    k, v = line.split("=", 1)
                    ingress_labels[k.strip()] = v.strip()
        except:
            pass

    # Ingress annotations
    ingress_annotations = {}
    if data.get("ingress_annotations"):
        try:
            # Parse ingress annotations if provided as key=value format
            for line in data["ingress_annotations"].split("\n"):
                if "=" in line:
                    k, v = line.split("=", 1)
                    ingress_annotations[k.strip()] = v.strip()
        except:
            pass

    # Container configuration
    container_data = data["container"]
    image = container_data["image"]

    # Ports
    ports = []
    for port_data in container_data.get("ports", []):
        ports.append(
            {
                "port": port_data["port"],
                "protocol": port_data.get("protocol", "TCP"),
                "expose_type": port_data.get("expose_type", "internal"),
            }
        )

    # Environment variables
    envs = {}
    if container_data.get("envs"):
        for line in container_data["envs"].split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                envs[k.strip()] = v.strip()

    # Files
    files = {}
    if container_data.get("files"):
        # Expect files in format: path=content (one per line)
        for line in container_data["files"].split("\n"):
            if "=" in line:
                path, content = line.split("=", 1)
                files[path.strip()] = content.strip()

    # Generate Go code
    main_go = generate_exposed_monopod(
        scenario_name=scenario_name,
        hostname=hostname,
        image=image,
        ports=ports,
        envs=envs if envs else None,
        files=files if files else None,
        limit_cpu=container_data.get("limit_cpu", "500m"),
        limit_memory=container_data.get("limit_memory", "256Mi"),
        packet_capture=container_data.get("packet_capture", True),
        packet_capture_pvc=packet_capture_pvc,
        connection_format=connection_format,
        ingress_namespace=ingress_namespace,
        ingress_labels=ingress_labels,
        ingress_annotations=ingress_annotations if ingress_annotations else None,
        image_pull_secrets=[data["image_pull_secrets"]]
        if data.get("image_pull_secrets")
        else None,
    )

    return {
        "main_go": main_go,
        "go_mod": generate_go_mod(scenario_name),
        "pulumi_yaml": generate_pulumi_yaml(scenario_name),
    }


def build_multipod_scenario(data):
    """Build Multipod scenario using Go generator.

    Returns a dict with:
        - main_go: main.go content
        - go_mod: go.mod content
        - pulumi_yaml: Pulumi.yaml content
    """
    scenario_name = data.get("identity", "scenario")
    hostname = data.get("hostname", "example.com")
    packet_capture_pvc = data.get("packet_capture_pvc", "pcap-core")
    ingress_namespace = data.get("ingress_namespace", "networking")
    connection_format = data.get("connection_format", "nc %s")

    # Ingress labels
    ingress_labels = {"app": "traefik"}
    if data.get("ingress_labels"):
        try:
            for line in data["ingress_labels"].split("\n"):
                if "=" in line:
                    k, v = line.split("=", 1)
                    ingress_labels[k.strip()] = v.strip()
        except:
            pass

    # Ingress annotations
    ingress_annotations = {}
    if data.get("ingress_annotations"):
        try:
            for line in data["ingress_annotations"].split("\n"):
                if "=" in line:
                    k, v = line.split("=", 1)
                    ingress_annotations[k.strip()] = v.strip()
        except:
            pass

    # Parse containers
    containers = {}
    for container_data in data.get("containers", []):
        name = container_data["name"]
        image = container_data["image"]

        # Ports
        ports = []
        for port_data in container_data.get("ports", []):
            ports.append(
                {
                    "port": port_data["port"],
                    "protocol": port_data.get("protocol", "TCP"),
                    "expose_type": port_data.get("expose_type", "internal"),
                }
            )

        # Envs
        envs = {}
        if container_data.get("envs"):
            for line in container_data["envs"].split("\n"):
                if "=" in line:
                    k, v = line.split("=", 1)
                    envs[k.strip()] = v.strip()

        # Files
        files = {}
        if container_data.get("files"):
            for line in container_data["files"].split("\n"):
                if "=" in line:
                    path, content = line.split("=", 1)
                    files[path.strip()] = content.strip()

        containers[name] = {
            "image": image,
            "ports": ports,
            "envs": envs,
            "files": files,
            "limit_cpu": container_data.get("limit_cpu"),
            "limit_memory": container_data.get("limit_memory"),
            "packet_capture": container_data.get("packet_capture", False),
        }

    # Parse rules
    rules = []
    for rule_data in data.get("rules", []):
        # Parse ports - can be single port or comma-separated
        ports_str = rule_data.get("ports", "")
        if isinstance(ports_str, str) and "," in ports_str:
            port_list = [int(p.strip()) for p in ports_str.split(",") if p.strip()]
        else:
            port_list = [int(ports_str)] if ports_str else []

        # Create a rule for each port
        for port in port_list:
            rules.append(
                {
                    "from": rule_data["from_container"],
                    "to": rule_data["to_container"],
                    "port": port,
                }
            )

    # Generate Go code
    main_go = generate_exposed_multipod(
        scenario_name=scenario_name,
        hostname=hostname,
        containers=containers,
        rules=rules,
        packet_capture_pvc=packet_capture_pvc,
        connection_format=connection_format,
        ingress_namespace=ingress_namespace,
        ingress_labels=ingress_labels,
        ingress_annotations=ingress_annotations if ingress_annotations else None,
        image_pull_secrets=[data["image_pull_secrets"]]
        if data.get("image_pull_secrets")
        else None,
    )

    return {
        "main_go": main_go,
        "go_mod": generate_go_mod(scenario_name),
        "pulumi_yaml": generate_pulumi_yaml(scenario_name),
    }


def build_kompose_scenario(data):
    """Build Kompose scenario using Go generator.

    Returns a dict with:
        - main_go: main.go content
        - go_mod: go.mod content
        - pulumi_yaml: Pulumi.yaml content
        - docker_compose_yaml: docker-compose.yaml content
    """
    scenario_name = data.get("identity", "scenario")
    hostname = data.get("hostname", "example.com")
    compose_yaml = data.get("compose_yaml", "")
    packet_capture_pvc = data.get("packet_capture_pvc", "pcap-core")
    ingress_namespace = data.get("ingress_namespace", "networking")
    connection_format = data.get("connection_format", "nc %s")

    # Ingress labels
    ingress_labels = {"app": "traefik"}
    if data.get("ingress_labels"):
        try:
            for line in data["ingress_labels"].split("\n"):
                if "=" in line:
                    k, v = line.split("=", 1)
                    ingress_labels[k.strip()] = v.strip()
        except:
            pass

    # Ingress annotations
    ingress_annotations = {}
    if data.get("ingress_annotations"):
        try:
            for line in data["ingress_annotations"].split("\n"):
                if "=" in line:
                    k, v = line.split("=", 1)
                    ingress_annotations[k.strip()] = v.strip()
        except:
            pass

    # Parse service ports
    ports = {}
    for service_name, ports_data in data.get("service_ports", {}).items():
        service_ports = []
        for port_data in ports_data:
            service_ports.append(
                {
                    "port": port_data["port"],
                    "protocol": port_data.get("protocol", "TCP"),
                    "expose_type": port_data.get("expose_type", "internal"),
                }
            )
        ports[service_name] = service_ports

    # Generate Go code
    main_go, docker_compose = generate_kompose(
        scenario_name=scenario_name,
        hostname=hostname,
        yaml_content=compose_yaml,
        ports=ports,
        packet_capture_pvc=packet_capture_pvc,
        connection_format=connection_format,
        ingress_namespace=ingress_namespace,
        ingress_labels=ingress_labels,
        ingress_annotations=ingress_annotations if ingress_annotations else None,
    )

    return {
        "main_go": main_go,
        "go_mod": generate_go_mod(scenario_name),
        "pulumi_yaml": generate_pulumi_yaml(scenario_name),
        "docker_compose_yaml": docker_compose,
    }


def create_scenario_zip(scenario, scenario_name):
    """Create a ZIP file containing the Go scenario files.

    Args:
        scenario: Dict with keys like main_go, go_mod, pulumi_yaml, etc.
        scenario_name: Name of the scenario

    Returns:
        BytesIO object containing the ZIP file
    """
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add main.go
        zf.writestr("main.go", scenario["main_go"])

        # Add go.mod
        zf.writestr("go.mod", scenario["go_mod"])

        # Add go.sum (required by chall-manager for validation)
        # Use the template go.sum from templates/go directory
        go_sum_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "templates",
            "go",
            "go.sum",
        )
        if os.path.exists(go_sum_path):
            with open(go_sum_path, "r") as f:
                zf.writestr("go.sum", f.read())

        # Add Pulumi.yaml
        zf.writestr("Pulumi.yaml", scenario["pulumi_yaml"])

        # Add docker-compose.yaml if it exists (for Kompose scenarios)
        if "docker_compose_yaml" in scenario:
            zf.writestr("docker-compose.yaml", scenario["docker_compose_yaml"])

    memory_file.seek(0)
    return memory_file

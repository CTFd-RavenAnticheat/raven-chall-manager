# Chall-Manager Python SDK

A Python SDK for generating Pulumi scenarios for chall-manager. This SDK provides a type-safe, Pythonic way to create deployment scenarios for CTF challenges.

## Features

- **Three Scenario Types**: Support for Monopod (single container), Multipod (multi-container), and Kompose (Docker Compose) deployments
- **Type-Safe**: Full type hints and validation
- **Fluent Builder API**: Easy-to-use builder pattern for creating scenarios
- **Private Registry Support**: Built-in support for image pull secrets
- **Packet Capture**: Optional packet capture sidecar for network analysis
- **Flexible Networking**: Support for Ingress, NodePort, LoadBalancer, and internal services

## Installation

```bash
# From the repository root
pip install -e sdk/python/

# Or install from PyPI (when published)
pip install chall-manager
```

## Quick Start

### Monopod (Single Container)

```python
from chall_manager import ScenarioBuilder, Container, PortBinding, ExposeType

# Create a simple web challenge
scenario = (ScenarioBuilder()
    .with_identity("web-challenge")
    .with_hostname("ctf.example.com")
    .with_container(
        Container(
            name="web",
            image="nginx:latest",
            ports=[
                PortBinding(80, expose_type=ExposeType.INGRESS),
            ],
            envs={"FLAG": "CTF{example_flag}"},
        )
    )
    .build_monopod())

# Generate Pulumi Python code
pulumi_code = scenario.generate_pulumi_code()

# Save to file
scenario.to_file("web_challenge.py")
```

### Multipod (Multi-Container)

```python
from chall_manager import ScenarioBuilder, Container, PortBinding, ExposeType

# Create a multi-tier application
scenario = (ScenarioBuilder()
    .with_identity("multi-tier-app")
    .with_container_named(
        "web",
        Container(
            name="web",
            image="nginx:latest",
            ports=[PortBinding(80, expose_type=ExposeType.INGRESS)],
        )
    )
    .with_container_named(
        "api",
        Container(
            name="api",
            image="myapi:latest",
            ports=[PortBinding(8080)],
        )
    )
    .with_container_named(
        "db",
        Container(
            name="db",
            image="postgres:14",
            ports=[PortBinding(5432)],
        )
    )
    # Define network rules between containers
    .with_rule("web", "api", ports=[8080])
    .with_rule("api", "db", ports=[5432])
    .build_multipod())

scenario.to_file("multi_tier.py")
```

### Kompose (Docker Compose)

```python
from chall_manager import ScenarioBuilder, PortBinding, ExposeType

docker_compose = """
version: '3.8'
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
  api:
    image: myapi:latest
    ports:
      - "8080:8080"
"""

scenario = (ScenarioBuilder()
    .with_identity("compose-challenge")
    .with_docker_compose(docker_compose)
    .with_service_ports("web", [
        PortBinding(80, expose_type=ExposeType.INGRESS),
    ])
    .with_packet_capture_for("web", enabled=True)
    .build_kompose())

scenario.to_file("compose_challenge.py")
```

## Advanced Features

### Private Registry Authentication

```python
scenario = (ScenarioBuilder()
    .with_identity("private-challenge")
    .with_image_pull_secrets(["gitlab-registry", "dockerhub-credentials"])
    .with_container(
        Container(
            name="app",
            image="registry.gitlab.com/ctf/private-app:v1.0.0",
            ports=[PortBinding(8080, expose_type=ExposeType.INGRESS)],
        )
    )
    .build_monopod())
```

### Packet Capture

Enable packet capture for network analysis:

```python
scenario = (ScenarioBuilder()
    .with_identity("pcap-challenge")
    .with_packet_capture_pvc("shared-captures")
    .with_container(
        Container(
            name="web",
            image="nginx:latest",
            ports=[PortBinding(80)],
            packet_capture=True,  # Enable packet capture
        )
    )
    .build_monopod())
```

### Resource Limits

```python
scenario = (ScenarioBuilder()
    .with_identity("limited-challenge")
    .with_container(
        Container(
            name="app",
            image="myapp:latest",
            ports=[PortBinding(8080)],
            limit_cpu="500m",
            limit_memory="512Mi",
        )
    )
    .build_monopod())
```

### File Mounts

```python
scenario = (ScenarioBuilder()
    .with_identity("file-challenge")
    .with_container(
        Container(
            name="app",
            image="nginx:latest",
            ports=[PortBinding(80)],
            files={
                "/app/config.json": '{"debug": false}',
                "/app/flags.txt": "CTF{hidden_flag}",
            },
        )
    )
    .build_monopod())
```

## Convenience Functions

For quick scenarios, use the convenience functions:

```python
from chall_manager import quick_monopod, quick_multipod, quick_kompose

# Quick monopod
scenario = quick_monopod(
    identity="quick-web",
    image="nginx:latest",
    port=80,
    hostname="ctf.example.com",
    expose_type=ExposeType.INGRESS,
)

# Quick multipod
containers = {
    "web": Container(name="web", image="nginx", ports=[PortBinding(80)]),
    "api": Container(name="api", image="myapi", ports=[PortBinding(8080)]),
}
scenario = quick_multipod(
    identity="quick-multi",
    containers=containers,
)

# Quick kompose
scenario = quick_kompose(
    identity="quick-compose",
    yaml_content=docker_compose_yaml,
)
```

## Configuration Reference

### Container Options

- `name`: Container name (required)
- `image`: Container image (required)
- `ports`: List of PortBinding objects
- `envs`: Dictionary of environment variables
- `files`: Dictionary of file paths to content
- `limit_cpu`: CPU limit (e.g., "500m")
- `limit_memory`: Memory limit (e.g., "512Mi")
- `packet_capture`: Enable packet capture (bool)

### PortBinding Options

- `port`: Port number (required)
- `protocol`: "TCP" or "UDP" (default: "TCP")
- `expose_type`: INTERNAL, NODE_PORT, LOAD_BALANCER, or INGRESS
- `annotations`: Dictionary of ingress annotations

### ScenarioBuilder Options

- `with_identity()`: Set scenario identity
- `with_hostname()`: Set hostname for ingress
- `with_image_pull_secrets()`: Set image pull secrets
- `with_packet_capture_pvc()`: Set packet capture PVC
- `with_additional()`: Add additional configuration

## Generated Pulumi Code

The SDK generates Pulumi Python code that can be deployed with:

```bash
pulumi up
```

The generated code includes:
- Namespace creation
- ConfigMaps for files
- Deployments with proper labels
- Services for exposed ports
- Ingress resources (when configured)
- NetworkPolicies (for Multipod)
- Packet capture sidecars (when enabled)

## Integration with Chall-Manager

After generating the Pulumi code, integrate with chall-manager:

```bash
# Create the challenge
chall-manager-cli challenge create \
    --id web-challenge \
    --scenario registry.example.com/scenarios/web:latest \
    --image-pull-secrets gitlab-registry
```

## Examples

See `examples.py` for comprehensive examples of all scenario types.

## License

Apache License 2.0
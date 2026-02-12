# Chall-Manager Python SDK - Structure

## File Organization

```
sdk/python/
├── setup.py                          # Package installation configuration
├── README.md                         # Documentation
├── examples.py                       # Usage examples
└── chall_manager/                    # Main package
    ├── __init__.py                   # Package exports
    ├── base.py                       # Base Scenario class and config
    ├── containers.py                 # Container, PortBinding, Rule classes
    ├── builder.py                    # ScenarioBuilder fluent API
    ├── monopod.py                    # Monopod scenario implementation
    ├── multipod.py                   # Multipod scenario implementation
    └── kompose.py                    # Kompose scenario implementation
```

## Module Structure

### base.py
- `Scenario` - Abstract base class for all scenarios
- `ScenarioConfig` - Base configuration dataclass
- `MonopodConfig` - Monopod-specific configuration
- `MultipodConfig` - Multipod-specific configuration  
- `KomposeConfig` - Kompose-specific configuration
- `ValidationError` - Exception for validation failures

### containers.py
- `ExposeType` - Enum for service exposure types (INTERNAL, NODE_PORT, LOAD_BALANCER, INGRESS)
- `PortBinding` - Port configuration with protocol and exposure type
- `Container` - Container specification with image, ports, envs, files, resources
- `Rule` - Network rule for inter-container communication in Multipod

### builder.py
- `ScenarioBuilder` - Fluent builder pattern for creating scenarios
- `quick_monopod()` - Convenience function for simple Monopod scenarios
- `quick_multipod()` - Convenience function for simple Multipod scenarios
- `quick_kompose()` - Convenience function for simple Kompose scenarios

### monopod.py
- `MonopodScenario` - Single container scenario implementation
- Generates: Namespace, ConfigMap, Deployment, Service, Ingress

### multipod.py
- `MultipodScenario` - Multi-container scenario implementation
- Generates: Namespace, ConfigMaps, Deployments, Services, NetworkPolicies

### kompose.py
- `KomposeScenario` - Docker Compose to Kubernetes scenario
- Generates: Namespace, ConfigMap (for packet capture), Deployments, Services

## Key Features

### 1. Type Safety
Full type hints throughout for IDE support and validation

### 2. Validation
Each scenario validates its configuration before generation

### 3. Modularity
- Separate modules for each scenario type
- Common base classes for shared functionality
- Builder pattern for flexible configuration

### 4. Generated Code Structure
All scenarios generate Pulumi Python code with:
- Namespace creation
- Proper labels and selectors
- ConfigMaps for file injection
- Deployments with containers
- Services for port exposure
- Ingress resources (when configured)
- NetworkPolicies (Multipod only)
- Packet capture sidecars (when enabled)

### 5. Advanced Features
- Private registry support (image pull secrets)
- Packet capture for network analysis
- Resource limits (CPU/memory)
- File injection via ConfigMaps
- Flexible networking (Ingress, NodePort, LoadBalancer)

## Usage Patterns

### Pattern 1: Builder Pattern (Recommended)
```python
from chall_manager import ScenarioBuilder, Container, PortBinding, ExposeType

scenario = (ScenarioBuilder()
    .with_identity("my-challenge")
    .with_hostname("ctf.example.com")
    .with_image_pull_secrets(["registry-secret"])
    .with_container(
        Container(
            name="web",
            image="nginx:latest",
            ports=[PortBinding(80, expose_type=ExposeType.INGRESS)],
        )
    )
    .build_monopod())

scenario.to_file("challenge.py")
```

### Pattern 2: Direct Configuration
```python
from chall_manager.monopod import MonopodScenario, MonopodConfig
from chall_manager.containers import Container, PortBinding

config = MonopodConfig(
    identity="my-challenge",
    hostname="ctf.example.com",
    container=Container(
        name="web",
        image="nginx:latest",
        ports=[PortBinding(80)],
    ),
)

scenario = MonopodScenario(config)
scenario.validate()
scenario.to_file("challenge.py")
```

### Pattern 3: Convenience Functions
```python
from chall_manager import quick_monopod

scenario = quick_monopod(
    identity="quick-challenge",
    image="nginx:latest",
    port=80,
    hostname="ctf.example.com",
)

scenario.to_file("challenge.py")
```

## Installation

```bash
cd sdk/python
pip install -e .
```

## Running Examples

```bash
cd sdk/python
python examples.py
```

This will generate example scenario files in the current directory.

## Integration with Pulumi

Generated files are standard Pulumi Python programs:

```bash
# After generating challenge.py
pulumi new python
# Copy challenge.py to __main__.py or import it
pulumi up
```

## Integration with Chall-Manager

Once deployed, register with chall-manager:

```bash
chall-manager-cli challenge create \
    --id my-challenge \
    --scenario registry.example.com/scenarios/my-challenge:latest \
    --image-pull-secrets registry-secret
```
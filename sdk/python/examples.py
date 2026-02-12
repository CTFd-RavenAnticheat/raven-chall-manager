"""
Examples of using the Chall-Manager Python SDK
"""

from chall_manager import (
    ScenarioBuilder,
    Container,
    PortBinding,
    Rule,
    ExposeType,
    quick_monopod,
    quick_multipod,
    quick_kompose,
)


def example_monopod_simple():
    """Simple Monopod example - single container web challenge."""
    # Using the builder pattern
    scenario = (
        ScenarioBuilder()
        .with_identity("web-challenge")
        .with_hostname("ctf.example.com")
        .with_container(
            Container(
                name="web",
                image="nginx:latest",
                ports=[
                    PortBinding(80, expose_type=ExposeType.INGRESS),
                ],
                envs={
                    "FLAG": "CTF{example_flag}",
                },
            )
        )
        .build_monopod()
    )

    # Generate Pulumi code
    pulumi_code = scenario.generate_pulumi_code()
    scenario.to_file("web_challenge.py")

    print("Generated Monopod scenario for web challenge")
    return scenario


def example_monopod_advanced():
    """Advanced Monopod with private registry and packet capture."""
    scenario = (
        ScenarioBuilder()
        .with_identity("advanced-web")
        .with_hostname("advanced.ctf.example.com")
        .with_image_pull_secrets(["gitlab-registry", "dockerhub"])
        .with_packet_capture_pvc("shared-captures")
        .with_additional("challenge_type", "web")
        .with_additional("difficulty", "hard")
        .with_container(
            Container(
                name="app",
                image="registry.gitlab.com/ctf/advanced-app:v1.0.0",
                ports=[
                    PortBinding(8080, expose_type=ExposeType.INGRESS),
                    PortBinding(8443, expose_type=ExposeType.LOAD_BALANCER),
                ],
                envs={
                    "DATABASE_URL": "postgres://db:5432/app",
                    "SECRET_KEY": "super-secret",
                },
                files={
                    "/app/config.json": '{"debug": false}',
                    "/app/flags.txt": "CTF{hidden_flag}",
                },
                limit_cpu="500m",
                limit_memory="512Mi",
                packet_capture=True,
            )
        )
        .build_monopod()
    )

    scenario.to_file("advanced_web.py")
    print("Generated advanced Monopod scenario")
    return scenario


def example_multipod():
    """Multipod example - web + database + cache."""
    scenario = (
        ScenarioBuilder()
        .with_identity("multi-tier-app")
        .with_hostname("multi.ctf.example.com")
        .with_container_named(
            "web",
            Container(
                name="web",
                image="nginx:latest",
                ports=[
                    PortBinding(80, expose_type=ExposeType.INGRESS),
                ],
                envs={"DB_HOST": "db"},
            ),
        )
        .with_container_named(
            "api",
            Container(
                name="api",
                image="myapi:latest",
                ports=[
                    PortBinding(8080),
                ],
                envs={"REDIS_HOST": "cache"},
            ),
        )
        .with_container_named(
            "db",
            Container(
                name="db",
                image="postgres:14",
                ports=[
                    PortBinding(5432),
                ],
                envs={"POSTGRES_PASSWORD": "secret"},
            ),
        )
        .with_container_named(
            "cache",
            Container(
                name="cache",
                image="redis:7",
                ports=[
                    PortBinding(6379),
                ],
            ),
        )
        # Define network rules
        .with_rule("web", "api", ports=[8080])
        .with_rule("api", "db", ports=[5432])
        .with_rule("api", "cache", ports=[6379])
        .build_multipod()
    )

    scenario.to_file("multi_tier.py")
    print("Generated Multipod scenario")
    return scenario


def example_kompose():
    """Kompose example - using existing Docker Compose."""
    docker_compose = """
version: '3.8'
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
    environment:
      - FLAG=CTF{docker_compose_flag}
    volumes:
      - ./html:/usr/share/nginx/html
  
  api:
    image: myapi:latest
    ports:
      - "8080:8080"
    environment:
      - DATABASE_URL=postgres://db:5432/app
  
  db:
    image: postgres:14
    environment:
      - POSTGRES_PASSWORD=secret
"""

    scenario = (
        ScenarioBuilder()
        .with_identity("compose-challenge")
        .with_docker_compose(docker_compose)
        .with_service_ports(
            "web",
            [
                PortBinding(80, expose_type=ExposeType.INGRESS),
            ],
        )
        .with_service_ports(
            "api",
            [
                PortBinding(8080, expose_type=ExposeType.INTERNAL),
            ],
        )
        .with_packet_capture_for("web", enabled=True)
        .with_packet_capture_for("api", enabled=True)
        .with_packet_capture_pvc("pcap-storage")
        .build_kompose()
    )

    scenario.to_file("compose_challenge.py")
    print("Generated Kompose scenario")
    return scenario


def example_quick_monopod():
    """Quick Monopod using convenience function."""
    scenario = quick_monopod(
        identity="quick-challenge",
        image="python:3.11-slim",
        port=5000,
        hostname="quick.ctf.example.com",
        expose_type=ExposeType.NODE_PORT,
    )

    scenario.to_file("quick_challenge.py")
    print("Generated quick Monopod scenario")
    return scenario


def example_quick_multipod():
    """Quick Multipod using convenience function."""
    containers = {
        "frontend": Container(
            name="frontend",
            image="nginx:latest",
            ports=[PortBinding(80, expose_type=ExposeType.INGRESS)],
        ),
        "backend": Container(
            name="backend",
            image="python:3.11",
            ports=[PortBinding(5000)],
        ),
    }

    scenario = quick_multipod(
        identity="quick-multi",
        containers=containers,
        hostname="multi.ctf.example.com",
    )

    scenario.to_file("quick_multi.py")
    print("Generated quick Multipod scenario")
    return scenario


def example_cli_usage():
    """Example of using with chall-manager CLI."""
    print("""
# After generating the Pulumi code, you can use it with chall-manager:

# 1. Install the Python SDK
pip install -e sdk/python/

# 2. Create a scenario using Python
python -c "
from examples import example_monopod_simple
scenario = example_monopod_simple()
"

# 3. The generated Pulumi code will be in web_challenge.py
# You can then use it with Pulumi:
pulumi up

# Or integrate with chall-manager CLI:
chall-manager-cli challenge create \\
    --id web-challenge \\
    --scenario registry.example.com/scenarios/web:latest \\
    --image-pull-secrets my-registry-secret
""")


if __name__ == "__main__":
    print("Chall-Manager Python SDK Examples")
    print("=" * 50)

    # Run examples
    example_monopod_simple()
    example_monopod_advanced()
    example_multipod()
    example_kompose()
    example_quick_monopod()
    example_quick_multipod()

    print("\n" + "=" * 50)
    print("All examples generated successfully!")
    print("Check the generated .py files in the current directory.")

    example_cli_usage()

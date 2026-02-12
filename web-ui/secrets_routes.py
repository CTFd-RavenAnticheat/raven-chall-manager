"""Secret management routes for chall-manager web UI."""

from flask import Blueprint, jsonify, request
import base64
import json
from datetime import datetime

# This would normally use the Kubernetes Python client
# For now, we'll create a mock implementation that shows the structure

secrets_bp = Blueprint("secrets", __name__, url_prefix="/api/secrets")


@secrets_bp.route("/list", methods=["GET"])
def list_secrets():
    """List all secrets in the chall-manager namespace."""
    try:
        # This would use kubernetes.client.CoreV1Api().list_namespaced_secret()
        # For demonstration, returning mock data
        secrets = [
            {
                "name": "gitlab-registry",
                "type": "kubernetes.io/dockerconfigjson",
                "created": "2024-02-12T10:30:00Z",
                "data_keys": [".dockerconfigjson"],
                "in_use_by": ["web-challenge", "crypto-challenge"],
            },
            {
                "name": "challenge-flags",
                "type": "Opaque",
                "created": "2024-02-12T11:00:00Z",
                "data_keys": ["flag1", "flag2"],
                "in_use_by": [],
            },
        ]
        return jsonify({"secrets": secrets})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@secrets_bp.route("/create/docker-registry", methods=["POST"])
def create_docker_registry_secret():
    """Create a docker registry secret."""
    try:
        data = request.get_json()

        name = data.get("name")
        server = data.get("server")
        username = data.get("username")
        password = data.get("password")
        email = data.get("email", "")
        namespace = data.get("namespace", "chall-manager")

        if not all([name, server, username, password]):
            return jsonify({"error": "Missing required fields"}), 400

        # Create docker config JSON
        auth_str = base64.b64encode(f"{username}:{password}".encode()).decode()
        docker_config = {
            "auths": {
                server: {
                    "username": username,
                    "password": password,
                    "email": email,
                    "auth": auth_str,
                }
            }
        }

        docker_config_json = json.dumps(docker_config)
        docker_config_b64 = base64.b64encode(docker_config_json.encode()).decode()

        # This would use kubernetes.client.CoreV1Api().create_namespaced_secret()
        # For demonstration, returning success
        secret_manifest = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": name,
                "namespace": namespace,
                "labels": {
                    "app.kubernetes.io/managed-by": "chall-manager-web-ui",
                    "chall-manager.ctfer.io/secret-type": "docker-registry",
                },
            },
            "type": "kubernetes.io/dockerconfigjson",
            "data": {".dockerconfigjson": docker_config_b64},
        }

        return jsonify(
            {
                "success": True,
                "message": f"Secret '{name}' created successfully in namespace '{namespace}'",
                "secret_name": name,
                "namespace": namespace,
                "manifest": secret_manifest,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@secrets_bp.route("/create/generic", methods=["POST"])
def create_generic_secret():
    """Create a generic opaque secret."""
    try:
        data = request.get_json()

        name = data.get("name")
        namespace = data.get("namespace", "chall-manager")
        secret_data = data.get("data", {})

        if not name:
            return jsonify({"error": "Secret name is required"}), 400

        if not secret_data:
            return jsonify({"error": "Secret data is required"}), 400

        # Base64 encode all data values
        encoded_data = {}
        for key, value in secret_data.items():
            if key and value:
                encoded_data[key] = base64.b64encode(value.encode()).decode()

        secret_manifest = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": name,
                "namespace": namespace,
                "labels": {
                    "app.kubernetes.io/managed-by": "chall-manager-web-ui",
                    "chall-manager.ctfer.io/secret-type": "generic",
                },
            },
            "type": "Opaque",
            "data": encoded_data,
        }

        return jsonify(
            {
                "success": True,
                "message": f"Secret '{name}' created successfully",
                "secret_name": name,
                "namespace": namespace,
                "manifest": secret_manifest,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@secrets_bp.route("/create/tls", methods=["POST"])
def create_tls_secret():
    """Create a TLS secret."""
    try:
        data = request.get_json()

        name = data.get("name")
        namespace = data.get("namespace", "chall-manager")
        cert = data.get("cert")
        key = data.get("key")

        if not all([name, cert, key]):
            return jsonify({"error": "Missing required fields: name, cert, key"}), 400

        secret_manifest = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": name,
                "namespace": namespace,
                "labels": {
                    "app.kubernetes.io/managed-by": "chall-manager-web-ui",
                    "chall-manager.ctfer.io/secret-type": "tls",
                },
            },
            "type": "kubernetes.io/tls",
            "data": {
                "tls.crt": base64.b64encode(cert.encode()).decode(),
                "tls.key": base64.b64encode(key.encode()).decode(),
            },
        }

        return jsonify(
            {
                "success": True,
                "message": f"TLS secret '{name}' created successfully",
                "secret_name": name,
                "namespace": namespace,
                "manifest": secret_manifest,
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@secrets_bp.route("/delete/<secret_name>", methods=["DELETE"])
def delete_secret(secret_name):
    """Delete a secret."""
    try:
        namespace = request.args.get("namespace", "chall-manager")

        # This would use kubernetes.client.CoreV1Api().delete_namespaced_secret()
        return jsonify(
            {
                "success": True,
                "message": f"Secret '{secret_name}' deleted from namespace '{namespace}'",
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@secrets_bp.route("/test-registry", methods=["POST"])
def test_registry_connection():
    """Test if registry credentials work."""
    try:
        data = request.get_json()
        server = data.get("server")
        username = data.get("username")
        password = data.get("password")

        # In a real implementation, this would attempt to login to the registry
        # For now, simulate a successful connection
        return jsonify(
            {
                "success": True,
                "message": f"Successfully connected to {server}",
                "details": {
                    "server": server,
                    "username": username,
                    "authenticated": True,
                },
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

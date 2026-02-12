"""
Secret management routes.
"""

from flask import Blueprint, jsonify, request
import requests
import os

secrets_bp = Blueprint("secrets", __name__, url_prefix="/api/secrets")

CHALL_MANAGER_URL = os.environ.get("CHALL_MANAGER_URL", "http://localhost:8080")


@secrets_bp.route("/list", methods=["GET"])
def list_secrets():
    """List all secrets via chall-manager."""
    try:
        namespace = request.args.get("namespace", "")
        url = f"{CHALL_MANAGER_URL}/api/v1/secrets"
        if namespace:
            url += f"?namespace={namespace}"

        response = requests.get(url, timeout=30)

        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify(
                {"error": f"Failed to list secrets: {response.text}"}
            ), response.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@secrets_bp.route("/create/docker-registry", methods=["POST"])
def create_docker_registry_secret():
    """Create Docker registry secret via chall-manager."""
    try:
        data = request.get_json()

        response = requests.post(
            f"{CHALL_MANAGER_URL}/api/v1/secrets/docker-registry", json=data, timeout=30
        )

        if response.status_code in [200, 201]:
            return jsonify({"success": True, "secret": response.json()})
        else:
            return jsonify(
                {"error": f"Failed to create secret: {response.text}"}
            ), response.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@secrets_bp.route("/create/generic", methods=["POST"])
def create_generic_secret():
    """Create generic secret via chall-manager."""
    try:
        data = request.get_json()

        response = requests.post(
            f"{CHALL_MANAGER_URL}/api/v1/secrets/generic", json=data, timeout=30
        )

        if response.status_code in [200, 201]:
            return jsonify({"success": True, "secret": response.json()})
        else:
            return jsonify(
                {"error": f"Failed to create secret: {response.text}"}
            ), response.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@secrets_bp.route("/create/tls", methods=["POST"])
def create_tls_secret():
    """Create TLS secret via chall-manager."""
    try:
        data = request.get_json()

        response = requests.post(
            f"{CHALL_MANAGER_URL}/api/v1/secrets/tls", json=data, timeout=30
        )

        if response.status_code in [200, 201]:
            return jsonify({"success": True, "secret": response.json()})
        else:
            return jsonify(
                {"error": f"Failed to create secret: {response.text}"}
            ), response.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@secrets_bp.route("/delete/<secret_name>", methods=["DELETE"])
def delete_secret(secret_name):
    """Delete secret via chall-manager."""
    try:
        namespace = request.args.get("namespace", "default")

        response = requests.delete(
            f"{CHALL_MANAGER_URL}/api/v1/secrets/{secret_name}?namespace={namespace}",
            timeout=30,
        )

        if response.status_code in [200, 204]:
            return jsonify(
                {"success": True, "message": f"Secret {secret_name} deleted"}
            )
        else:
            return jsonify(
                {"error": f"Failed to delete secret: {response.text}"}
            ), response.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@secrets_bp.route("/test-registry", methods=["POST"])
def test_registry_connection():
    """Test registry credentials via chall-manager."""
    try:
        data = request.get_json()

        response = requests.post(
            f"{CHALL_MANAGER_URL}/api/v1/secrets/test-registry", json=data, timeout=30
        )

        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify(
                {"error": f"Failed to test connection: {response.text}"}
            ), response.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500

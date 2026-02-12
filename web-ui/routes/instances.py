"""
Instance management routes.
"""

from flask import Blueprint, jsonify, request
import requests
import json
import os

instances_bp = Blueprint("instances", __name__, url_prefix="/api/chall-manager")

CHALL_MANAGER_URL = os.environ.get("CHALL_MANAGER_URL", "http://localhost:8080")


@instances_bp.route("/instances", methods=["GET"])
def list_instances():
    """List all instances."""
    try:
        response = requests.get(f"{CHALL_MANAGER_URL}/api/v1/instance", timeout=30)

        if response.status_code == 200:
            instances = []
            for line in response.iter_lines():
                if line:
                    instances.append(json.loads(line))
            return jsonify({"instances": instances})
        else:
            return jsonify(
                {"error": f"Failed to list instances: {response.status_code}"}
            ), response.status_code

    except Exception as e:
        return jsonify({"error": str(e)}), 500
